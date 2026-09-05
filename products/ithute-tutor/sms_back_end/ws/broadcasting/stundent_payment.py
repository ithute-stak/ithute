from fastapi.encoders import jsonable_encoder

from ws.connection_manager import socket_manager

async def student_payment_socket(data=None, notification=None):
    return await socket_manager.broadcast(
        jsonable_encoder({
            "event": "PAYMENT_COMPLETED",
            "channel": "finance",
            "data": data,
            "notification": notification,
        })
    )


async def grade_created_socket(data):
    return await socket_manager.broadcast({
        "event": "GRADE_CREATED",
        "channel": "academic",
        "data": data,
    })

async def class_created_socket(data):
    return await socket_manager.broadcast({
        "event": "CLASS_CREATED",
        "channel": "academic",
        "data": data
    })

async def teacher_created_socket(data):
    return await socket_manager.broadcast({
        "event": "TEACHER_CREATED",
        "channel": "academic",
        "data": data,
    })