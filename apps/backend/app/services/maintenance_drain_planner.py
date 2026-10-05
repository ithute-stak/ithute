from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import HostingDatabase, HostingNode, HostingProject, InfrastructureServer
from app.services.hosting_placement import rank_nodes
from app.services.database_replication import build_database_failover_plan
from app.services.smart_failover_ranking import rank_failover_candidates


def _server_for_node(db: Session, node_id) -> InfrastructureServer | None:
    return db.scalar(
        select(InfrastructureServer).where(InfrastructureServer.hosting_node_id == node_id)
    )


def _project_plan(db: Session, project: HostingProject, source_node_id) -> dict:
    attached_databases = db.scalars(
        select(HostingDatabase).where(
            HostingDatabase.project_id == project.id,
            HostingDatabase.status.notin_(["deleting", "deleted", "failed"]),
        )
    ).all()

    blockers: list[str] = []
    if project.failover_policy != "stateless_auto":
        blockers.append("project is not opted into stateless_auto relocation")
    database_failover_plans = [
        build_database_failover_plan(db, database=row)
        for row in attached_databases
    ]
    unsafe_databases = [
        plan for plan in database_failover_plans
        if not plan["promotion_ready"]
    ]
    if unsafe_databases:
        blockers.append("one or more managed database dependencies have no safe replica promotion target")

    ranked = rank_nodes(
        db,
        workload="application",
        storage_mb=project.storage_mb,
        memory_mb=project.memory_mb,
        cpu_millicores=project.cpu_millicores,
        tenant_id=project.tenant_id,
        lock=False,
    )
    candidates = [
        (row, _server_for_node(db, row["node"].id))
        for row in ranked
        if row["eligible"] and row["node"].id != source_node_id
    ]

    target = None
    ranking = []
    if not blockers and candidates:
        source_server = _server_for_node(db, source_node_id)
        ranking = rank_failover_candidates(
            db,
            source_server=source_server,
            candidates=candidates,
        )
        if ranking:
            best = ranking[0]
            if best["failure_domain"]["highest_risk"] not in {"physical_host", "network_segment"}:
                target = best["placement"]["node"]

    if not blockers and target is None:
        blockers.append("no safe eligible destination node is available")

    return {
        "kind": "application",
        "id": str(project.id),
        "name": project.name,
        "tenant_id": str(project.tenant_id),
        "status": project.status,
        "resource_request": {
            "cpu_millicores": project.cpu_millicores,
            "memory_mb": project.memory_mb,
            "storage_mb": project.storage_mb,
        },
        "dependencies": [
            {
                "kind": "database",
                "id": str(row.id),
                "engine": row.engine,
                "status": row.status,
                "promotion_ready": plan["promotion_ready"],
                "recommended_replica": plan["recommended_replica"],
            }
            for row, plan in zip(attached_databases, database_failover_plans)
        ],
        "movable": not blockers,
        "blockers": blockers,
        "recommended_target_node_id": str(target.id) if target else None,
        "recommended_target_name": target.name if target else None,
        "candidate_count": len(candidates),
    }


def _database_plan(db: Session, database: HostingDatabase) -> dict:
    failover = build_database_failover_plan(db, database=database)
    recommended = failover["recommended_replica"]
    return {
        "kind": "database",
        "id": str(database.id),
        "name": database.database_name,
        "tenant_id": str(database.tenant_id),
        "status": database.status,
        "resource_request": {
            "cpu_millicores": 0,
            "memory_mb": 0,
            "storage_mb": database.storage_mb,
        },
        "dependencies": [],
        "movable": bool(failover["promotion_ready"]),
        "blockers": list(failover["blockers"]),
        "recommended_target_node_id": recommended["node_id"] if recommended else None,
        "recommended_target_name": recommended["node_name"] if recommended else None,
        "candidate_count": len(failover["replicas"]),
        "failover_plan": failover,
    }


def build_maintenance_drain_plan(db: Session, *, node_id) -> dict:
    node = db.get(HostingNode, node_id)
    if node is None:
        raise ValueError("Hosting node not found")

    projects = db.scalars(
        select(HostingProject)
        .where(
            HostingProject.node_id == node.id,
            HostingProject.status != "suspended",
        )
        .order_by(HostingProject.created_at.asc(), HostingProject.id.asc())
    ).all()
    databases = db.scalars(
        select(HostingDatabase)
        .where(
            HostingDatabase.node_id == node.id,
            HostingDatabase.status.notin_(["deleting", "deleted", "failed"]),
        )
        .order_by(HostingDatabase.created_at.asc(), HostingDatabase.id.asc())
    ).all()

    project_rows = [_project_plan(db, project, node.id) for project in projects]
    database_rows = [_database_plan(db, database) for database in databases]

    # Databases are promoted/relocated before applications that depend on them.
    migration_order = database_rows + project_rows
    blockers = [
        {
            "kind": item["kind"],
            "id": item["id"],
            "name": item["name"],
            "reasons": item["blockers"],
        }
        for item in migration_order
        if item["blockers"]
    ]

    required = {
        "cpu_millicores": sum(item["resource_request"]["cpu_millicores"] for item in migration_order),
        "memory_mb": sum(item["resource_request"]["memory_mb"] for item in migration_order),
        "storage_mb": sum(item["resource_request"]["storage_mb"] for item in migration_order),
    }

    return {
        "node": {
            "id": str(node.id),
            "name": node.name,
            "status": node.status,
            "accepts_new_projects": node.accepts_new_projects,
        },
        "summary": {
            "projects": len(project_rows),
            "databases": len(database_rows),
            "movable_workloads": sum(1 for item in migration_order if item["movable"]),
            "blocked_workloads": len(blockers),
            "maintenance_ready": not blockers,
            "required_destination_capacity": required,
        },
        "migration_order": migration_order,
        "blockers": blockers,
        "execution_mode": "plan_only",
    }
