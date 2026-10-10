"""Bound API bodies before JSON/form parsing, including chunked transfers."""

from starlette.responses import JSONResponse


class ApiBodyLimitMiddleware:
    def __init__(self, app, limit) -> None:
        self.app = app
        self.limit = limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or "/api/" not in scope.get("path", ""):
            return await self.app(scope, receive, send)
        limit = self.limit()
        body = bytearray()
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse(
                {
                    "detail": {
                        "code": "BODY_LENGTH_INVALID",
                        "message": "Lungime invalidă.",
                    }
                },
                400,
            )(scope, receive, send)
        if declared > limit:
            return await self.reject(scope, receive, send)
        while True:
            chunk = await receive()
            if chunk["type"] == "http.disconnect":
                return
            data = chunk.get("body", b"")
            if len(body) + len(data) > limit:
                return await self.reject(scope, receive, send)
            body.extend(data)
            if not chunk.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    @staticmethod
    async def reject(scope, receive, send):
        await JSONResponse(
            {
                "detail": {
                    "code": "BODY_TOO_LARGE",
                    "message": "Cererea depășește limita permisă.",
                }
            },
            413,
        )(scope, receive, send)
