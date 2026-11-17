from flask import redirect, abort, current_app, request, Response
from functools import wraps
from srht.crypto import verify_encrypted_authorization
from srht.oauth import current_user, UserType
import json

def adminrequired(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user:
            return redirect(current_app.login_url)
        elif current_user.user_type != UserType.admin:
            abort(403)
        else:
            return f(*args, **kwargs)
    return wrapper

def internalwebhook(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        def fail():
            abort(Response(
                status=401,
                mimetype="application/json",
                response=json.dumps({
                    "errors": [
                        { "reason": "Internal request authorization failed." },
                    ]
                })))
        token = request.headers.get('Authorization')
        if not token or not token.startswith('Internal '):
            fail()
        token = token.split(' ')
        if len(token) != 2:
            fail()
        auth = verify_encrypted_authorization(token[1])
        return f(*args, **kwargs)
    return wrapper
