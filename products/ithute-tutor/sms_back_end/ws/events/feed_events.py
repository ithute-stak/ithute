from ws.connection_manager import socket_manager


async def feed_post_created_socket(data):
    return await socket_manager.broadcast({
        "event": "FEED_POST_CREATED",
        "channel": "feed",
        "data": data,
    })


async def feed_comment_created_socket(data):
    return await socket_manager.broadcast({
        "event": "FEED_COMMENT_CREATED",
        "channel": "feed",
        "data": data,
    })


async def feed_post_liked_socket(data):
    return await socket_manager.broadcast({
        "event": "FEED_POST_LIKED",
        "channel": "feed",
        "data": data,
    })


async def feed_post_shared_socket(data):
    return await socket_manager.broadcast({
        "event": "FEED_POST_SHARED",
        "channel": "feed",
        "data": data,
    })