from flask import Blueprint, jsonify

api_v1 = Blueprint("api_v1", __name__)

# Import route modules to register them with the Blueprint.
# Order matters: modules that reference api_v1 must be imported after it is created.
from . import analysis, assignments, export, import_, layout, library, manifest, preferences, sections, themes  # noqa: E402, F401


@api_v1.app_errorhandler(404)
def not_found(exc):
    if not _is_api_request():
        return exc
    return jsonify({"error": {"code": "not_found", "message": "Resource not found"}}), 404


@api_v1.app_errorhandler(405)
def method_not_allowed(exc):
    if not _is_api_request():
        return exc
    return jsonify({"error": {"code": "method_not_allowed", "message": "Method not allowed"}}), 405


@api_v1.app_errorhandler(500)
def internal_error(exc):
    if not _is_api_request():
        return exc
    return jsonify({"error": {"code": "internal_error", "message": "Internal server error"}}), 500


def _is_api_request() -> bool:
    from flask import request
    return request.path.startswith("/api/")
