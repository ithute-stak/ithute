"use client";

import { useEffect, useMemo, useState } from "react";
import { Plus, X } from "lucide-react";

import { listEmployerGroups } from "@/api/employerGroups";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SuggestionSearch } from "@/components/ui/suggestion-search";
import type { EmployerGroup, EmployerGroupCreate } from "@/types/employerGroup";

type Selection = {
  employer_group_id: string | null;
  employer_name: string | null;
  new_employer_group: EmployerGroupCreate | null;
};

type Props = {
  employerGroupId?: string | null;
  employerName?: string | null;
  newEmployerGroup?: EmployerGroupCreate | null;
  onChange: (selection: Selection) => void;
  required?: boolean;
};

function display(group: Pick<EmployerGroup, "code" | "name">): string {
  return `${group.code} — ${group.name}`;
}

export function EmployerGroupRegistrationField({
  employerGroupId,
  employerName,
  newEmployerGroup,
  onChange,
  required = false,
}: Props) {
  const [groups, setGroups] = useState<EmployerGroup[]>([]);
  const [search, setSearch] = useState("");
  const [adding, setAdding] = useState(false);
  const [draftCode, setDraftCode] = useState("");
  const [draftName, setDraftName] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void listEmployerGroups()
      .then((rows) => {
        if (!cancelled) {
          setGroups(rows);
          setLoadError(null);
        }
      })
      .catch(() => {
        if (!cancelled) setLoadError("Employer groups could not be loaded. You can still add a new group below.");
      });
    return () => { cancelled = true; };
  }, []);

  const selected = useMemo(
    () => groups.find((group) => group.id === employerGroupId) ?? null,
    [employerGroupId, groups],
  );

  useEffect(() => {
    if (selected) {
      setSearch(display(selected));
    } else if (newEmployerGroup) {
      setSearch(`${newEmployerGroup.code} — ${newEmployerGroup.name}`);
    } else if (employerName && !search) {
      setSearch(employerName);
    }
  }, [employerName, newEmployerGroup, search, selected]);

  const suggestions = useMemo(
    () => groups.map((group) => ({
      value: group.id,
      label: `${group.code} — ${group.name}`,
      description: group.name,
      keywords: [group.code, group.name],
    })),
    [groups],
  );

  function clearSelection(nextSearch = "") {
    setSearch(nextSearch);
    onChange({
      employer_group_id: null,
      employer_name: nextSearch.trim() || null,
      new_employer_group: null,
    });
  }

  function saveDraft() {
    const code = draftCode.trim().toUpperCase().replace(/\s+/g, " ");
    const name = draftName.trim().replace(/\s+/g, " ");
    if (!code || name.length < 2) return;
    const existing = groups.find((group) => group.code.toUpperCase() === code);
    if (existing) {
      setSearch(display(existing));
      setAdding(false);
      onChange({
        employer_group_id: existing.id,
        employer_name: existing.name,
        new_employer_group: null,
      });
      return;
    }
    setSearch(`${code} — ${name}`);
    setAdding(false);
    onChange({
      employer_group_id: null,
      employer_name: name,
      new_employer_group: { code, name },
    });
  }

  return (
    <div className="space-y-2">
      <div className="space-y-0.5">
        <Label className="text-sm font-bold">
          Employer / work group{required ? <span className="ml-1 text-destructive">*</span> : null}
        </Label>
        <p className="text-[11px] leading-4 text-muted-foreground">
          Search by code or employer name. Add a new code here if it is not already listed.
        </p>
      </div>
      <SuggestionSearch
        value={search}
        onValueChange={(value) => clearSelection(value)}
        suggestions={suggestions}
        placeholder="Search L/GOV, LMPS, LCS, LDF…"
        emptyMessage="No matching employer/work group."
        suggestionLabel="Employer / work groups"
        maxSuggestions={12}
        showSuggestionsOnFocus
        onSuggestionSelect={(suggestion) => {
          const group = groups.find((row) => row.id === suggestion.value);
          if (!group) return;
          setSearch(display(group));
          setAdding(false);
          onChange({
            employer_group_id: group.id,
            employer_name: group.name,
            new_employer_group: null,
          });
        }}
      />
      {loadError ? <p className="text-xs text-amber-700 dark:text-amber-300">{loadError}</p> : null}
      {newEmployerGroup ? (
        <div className="flex items-center justify-between rounded-xl border bg-muted/30 px-3 py-2 text-xs">
          <span><strong>{newEmployerGroup.code}</strong> · {newEmployerGroup.name} will be saved with this client.</span>
          <Button type="button" variant="ghost" size="icon" className="h-7 w-7" onClick={() => clearSelection("")}>
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      ) : null}
      {!adding ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            setDraftCode("");
            setDraftName(search.includes("—") ? search.split("—").slice(1).join("—").trim() : search.trim());
            setAdding(true);
          }}
        >
          <Plus className="h-4 w-4" />Add new employer/group
        </Button>
      ) : (
        <div className="rounded-2xl border bg-muted/20 p-3">
          <div className="grid gap-3 sm:grid-cols-[140px_1fr]">
            <div className="space-y-1">
              <Label className="text-xs font-semibold">Group code</Label>
              <Input value={draftCode} maxLength={40} onChange={(event) => setDraftCode(event.target.value)} placeholder="e.g. LMPS" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs font-semibold">Employer / group name</Label>
              <Input value={draftName} maxLength={200} onChange={(event) => setDraftName(event.target.value)} placeholder="Employer or work group" />
            </div>
          </div>
          <div className="mt-3 flex justify-end gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={() => setAdding(false)}>Cancel</Button>
            <Button type="button" size="sm" disabled={!draftCode.trim() || draftName.trim().length < 2} onClick={saveDraft}>
              Use this group
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
