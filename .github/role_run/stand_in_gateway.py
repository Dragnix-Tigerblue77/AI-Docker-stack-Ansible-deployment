#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tigerblue77
# SPDX-License-Identifier: AGPL-3.0-only
"""A stand-in for the endpoints of LiteLLM's admin API that the role calls after deploying.

CI only, for the "role run" jobs of ".github/workflows/ansible-ci.yml". With the Claude Code agent on,
which is the example playbook's default, the role registers the agent's virtual key in the gateway
once the stack is up, and the stand-in deployer starts no stack: without something answering on port
4000 the run waits out its retries and fails. This answers just enough for the run to reach its last
task, and holds the role to the calls it is written to make:

  GET  /health/readiness       200
  GET  /key/info?key=<sha256>  404 until that key was generated, 200 after (the role looks first)
  POST /key/generate           200, with the key, its alias and its model allow-list in the body: a list
                               of distinct non-empty strings, as LiteLLM's own "models" is (#307)
  POST /user/new               200 for a user it has not seen, 409 for one it has (by username or email); the
                               body must hold a user_id, a user_email, a user_role that is "internal_user" or
                               "proxy_admin" and "auto_create_key" false. The gateway's own administrator
                               identity, "default_user_id", needs no email, as in LiteLLM
  POST /invitation/new         200, with an id and an expiry, for a "proxy_admin" it created: the role invites
                               administrators only, and only the run that created them. 400, as LiteLLM does,
                               while "default_user_id" does not exist: LiteLLM records the master key's identity
                               as who made the invitation, a foreign key to its user table

Every call but the first must carry the master key as a bearer token. Anything else is answered 500 and
printed, so the role's task fails with the reason on the runner's log rather than a quiet success.

What this does NOT check is that real LiteLLM answers like this: the shapes are the role's reading of
its API, measured elsewhere. It checks the role makes the calls it says it makes.
"""

import hashlib
import http.server
import json
import pathlib
import sys
import urllib.parse

import yaml

VARS = pathlib.Path(__file__).with_name("vars.yml")
MASTER_KEY = yaml.safe_load(VARS.read_text())["vault_Artificial_Intelligence_LiteLLM_master_key"]
PORT = 4000
GENERATED = set()
USERS = {}
ROLES = ("internal_user", "proxy_admin")
ADMIN_IDENTITY = "default_user_id"


class Handler(http.server.BaseHTTPRequestHandler):
    def reply(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def refuse(self, why):
        print(f"stand-in gateway: refused {self.command} {self.path}: {why}", file=sys.stderr, flush=True)
        self.reply(500, {"error": why})

    def authorised(self):
        if self.headers.get("Authorization") != f"Bearer {MASTER_KEY}":
            self.refuse("the master key was not sent as a bearer token")
            return False
        return True

    def do_GET(self):  # noqa: N802 - the name http.server looks for
        url = urllib.parse.urlsplit(self.path)
        if url.path == "/health/readiness":
            self.reply(200, {"status": "healthy"})
        elif url.path == "/key/info":
            if not self.authorised():
                return
            key = urllib.parse.parse_qs(url.query).get("key", [""])[0]
            if key in GENERATED:
                self.reply(200, {"key": key, "info": {"status": "active"}})
            else:
                self.reply(404, {"error": "key not found"})
        else:
            self.refuse("no such endpoint in this stand-in")

    def do_POST(self):  # noqa: N802
        handlers = {"/key/generate": self.generate_key, "/user/new": self.new_user, "/invitation/new": self.new_invitation}
        if self.path not in handlers:
            self.refuse("no such endpoint in this stand-in")
            return
        if not self.authorised():
            return
        handlers[self.path](json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}"))

    def new_user(self, body):
        required = ("user_id", "user_role") if body.get("user_id") == ADMIN_IDENTITY else ("user_id", "user_email", "user_role")
        missing = [name for name in required if not isinstance(body.get(name), str) or not body[name]]
        if missing:
            self.refuse(f"the body lacks a string {', '.join(missing)}")
        elif body["user_role"] not in ROLES:
            self.refuse(f"user_role is {body['user_role']!r}, not one of {ROLES}")
        elif body.get("auto_create_key") is not False:
            self.refuse("auto_create_key is not false: LiteLLM would mint a key nobody is shown")
        elif body["user_id"] in USERS or body.get("user_email", "").lower() in {user["email"] for user in USERS.values()} - {""}:
            self.reply(409, {"error": "user already exists"})
        else:
            USERS[body["user_id"]] = {"email": body.get("user_email", "").lower(), "role": body["user_role"]}
            print(f"stand-in gateway: user {body['user_id']!r} created as {body['user_role']}", flush=True)
            self.reply(200, {"user_id": body["user_id"], "user_email": body.get("user_email"), "user_role": body["user_role"]})

    def new_invitation(self, body):
        user = USERS.get(body.get("user_id"))
        if user is None:
            self.refuse(f"invitation for a user this stand-in never created: {body.get('user_id')!r}")
        elif user["role"] != "proxy_admin":
            self.refuse("an invitation for a user who is not a proxy_admin: the role invites administrators only")
        elif ADMIN_IDENTITY not in USERS:
            self.reply(400, {"detail": {"error": "User id does not exist in 'LiteLLM_UserTable'. Fix this by creating user via `/user/new`."}})
        else:
            self.reply(200, {"id": f"invitation-{body['user_id']}", "user_id": body["user_id"], "is_accepted": False,
                             "expires_at": "2099-01-01T00:00:00Z"})

    def generate_key(self, body):
        missing = [name for name in ("key", "key_alias", "models") if not body.get(name)]
        if missing:
            self.refuse(f"the body lacks {', '.join(missing)}")
            return
        models = body["models"]
        well_formed = isinstance(models, list) and all(isinstance(name, str) and name for name in models)
        if not well_formed or len(set(models)) != len(models):
            self.refuse(f"models is not a list of distinct non-empty strings: {models!r}")
            return
        print(f"stand-in gateway: key {body['key_alias']!r} allows {models}", flush=True)
        GENERATED.add(hashlib.sha256(body["key"].encode()).hexdigest())
        self.reply(200, {"key": body["key"]})

    def log_message(self, format, *args):  # noqa: A002 - the signature http.server defines
        print("stand-in gateway:", format % args, flush=True)


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
