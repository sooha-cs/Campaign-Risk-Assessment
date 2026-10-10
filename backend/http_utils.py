"""Shared route helper, kept out of app.py so blueprints (monitoring.py) can import it without a circular import."""
import logging

from flask import jsonify

import ai_service
from errors import NotFoundError, ValidationError


def run(work):
    """Runs a route's logic and converts errors into clean JSON responses."""
    try:
        return jsonify(work())
    except ValidationError as e:
        return jsonify(error="Invalid input", details=e.errors), 400
    except NotFoundError as e:
        return jsonify(error=str(e)), 404
    except ai_service.AIError as e:
        return jsonify(error=str(e)), 502
    except Exception:  # noqa: BLE001
        logging.exception("Unexpected error")
        return jsonify(error="Internal server error"), 500
