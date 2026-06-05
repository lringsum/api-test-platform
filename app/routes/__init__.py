from flask import flash, jsonify, redirect, url_for

from app.services.base_service import ServiceError


def handle_page_error(message, endpoint):
    flash(message, "danger")
    return redirect(url_for(endpoint))


def handle_success(message, endpoint):
    flash(message, "success")
    return redirect(url_for(endpoint))


def json_success(message="", data=None):
    return jsonify({
        "success": True,
        "message": message,
        "data": data or {},
    })


def json_error(message, status_code=400):
    return jsonify({
        "success": False,
        "message": message,
        "data": {},
    }), status_code


def catch_service_error_json(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ServiceError as exc:
            return json_error(str(exc))
        except Exception as exc:
            return json_error(f"系统异常：{exc}", 500)

    wrapper.__name__ = func.__name__
    return wrapper
