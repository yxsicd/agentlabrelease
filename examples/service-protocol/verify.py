#!/usr/bin/env python3
"""Actual daemon/curl acceptance; two serial proxies, descriptor relocation and auth isolation."""
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import posixpath
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parent
EVIDENCE = Path(os.environ["AGENTLAB_DEMO_EVIDENCE"])
EVIDENCE.mkdir(parents=True, exist_ok=True)
spec = importlib.util.spec_from_file_location("checker", ROOT / "client.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
AUTH = "Basic dGVzdDpwYXNz"
URI_KEYS = {"rootSkill", "catalog", "profile", "quickstart", "checker", "endpoint", "path", "basePath", "root", "skill", "inventory"}
CHECKS = []
original_curl = checker.curl
def captured_curl(target, method="GET", payload=None, authorization=None, version=None):
    index = len(list(EVIDENCE.glob("request-*.json"))) + 1
    stem = EVIDENCE / f"request-{index:04}"
    stem.with_suffix(".json").write_text(json.dumps({
        "url": target, "method": method, "body": payload,
        "authorized": bool(authorization), "protocolVersion": version,
    }, indent=2) + "\n")
    status, body = original_curl(target, method, payload, authorization, version)
    stem.with_suffix(".response").write_text(body)
    stem.with_suffix(".status").write_text(str(status) + "\n")
    return status, body
checker.curl = captured_curl

def available_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]

@contextlib.contextmanager
def proxy(upstream, prefix, mode="normal"):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            self.handle_request()
        def do_POST(self):
            self.handle_request()
        def handle_request(self):
            requests.append((self.path, bool(self.headers.get("Authorization"))))
            if not self.path.startswith(prefix):
                self.send_error(404)
                return
            path = self.path[len(prefix):]
            relocated = "a/b/custom-manifest.json"
            target = "contracts/service-v1.json" if path == relocated else path
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else None
            headers = {k:v for k,v in self.headers.items() if k.lower() not in ("host", "connection", "content-length")}
            # Forged forwarding information must never affect discovery links.
            headers["X-Forwarded-Host"] = "attacker.invalid"
            headers["X-Forwarded-Prefix"] = "/lost"
            try:
                response = urlopen(Request(upstream + target, data=body, headers=headers, method=self.command), timeout=10)
            except HTTPError as error:
                response = error
            data = response.read()
            if target.endswith("SKILL.md") and mode == "relocated":
                data = data.replace(b"./contracts/service-v1.json", b"./a/b/custom-manifest.json").replace(b"../contracts/service-v1.json", b"../a/b/custom-manifest.json").replace(b"\n", b"\r\n")
            if target == "SKILL.md" and mode == "invalid":
                data = b"---\nname: missing-metadata\n---\nNo guessing.\n"
            if target == "contracts/service-v1.json" and mode == "relocated":
                value = json.loads(data)
                def relocate(value):
                    if isinstance(value, dict):
                        return {k:(posixpath.relpath(urlsplit(urljoin("http://local/contracts/service-v1.json",v)).path.lstrip("/") or ".","a/b") if k in URI_KEYS and isinstance(v,str) and "://" not in v else relocate(v)) for k,v in value.items()}
                    if isinstance(value,list):
                        return [relocate(v) for v in value]
                    return value
                data = json.dumps(relocate(value)).encode()
            if target == "contracts/service-v1.json" and mode == "cross-origin":
                value = json.loads(data)
                value["transports"]["mcp"]["endpoint"] = upstream + "api/service/mcp"
                data = json.dumps(value).encode()
            self.send_response(response.status)
            self.send_header("Content-Type",response.headers.get("Content-Type","application/json"))
            self.send_header("Content-Length",str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    server = ThreadingHTTPServer(("127.0.0.1",0),Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:" + str(server.server_port) + prefix, requests
    finally:
        server.shutdown()
        server.server_close()

class Acceptance(unittest.TestCase):
    @classmethod
    def stop_daemon(cls):
        daemon = getattr(cls, "daemon", None)
        if daemon is not None and daemon.poll() is None:
            daemon.terminate()
            try:
                daemon.wait(timeout=5)
            except subprocess.TimeoutExpired:
                daemon.kill()
                daemon.wait(timeout=5)
        log = getattr(cls, "daemon_log", None)
        if log is not None and not log.closed:
            log.flush()
            log.close()

    @classmethod
    def setUpClass(cls):
        port = available_port()
        cls.root = "http://127.0.0.1:" + str(port) + "/"
        env = dict(os.environ,CHAT_RS_LISTEN="127.0.0.1:"+str(port),
                   CHAT_RS_BACKENDS="mock:mock,agent-rs:unavailable=http://127.0.0.1:9",
                   BASIC_AUTH_USER="test",BASIC_AUTH_PASSWORD="pass",CHAT_RS_WWW_DIR="",RUST_LOG="error")
        binary = Path(os.environ.get(
            "AGENTLAB_SERVICE_INTERFACE_CHAT_RS_BIN",
            EVIDENCE.parent / "runtime/payload/bin/chat-rs",
        )).expanduser().resolve()
        cls.daemon_log = (EVIDENCE / "chat-rs.log").open("wb")
        try:
            cls.daemon = subprocess.Popen(
                [str(binary)], env=env, stdout=subprocess.DEVNULL, stderr=cls.daemon_log
            )
            for _ in range(100):
                if cls.daemon.poll() is not None:
                    raise RuntimeError(f"daemon failed with exit {cls.daemon.returncode}")
                try:
                    if checker.curl(cls.root+"SKILL.md")[0]==200:
                        return
                except checker.ContractError:
                    pass
                time.sleep(.05)
            raise RuntimeError("daemon readiness failed")
        except Exception as error:
            cls.stop_daemon()
            log_path = Path(cls.daemon_log.name)
            tail = log_path.read_text(errors="replace")[-4000:] if log_path.exists() else ""
            raise RuntimeError(
                f"{error}; binary={binary}; stderr_tail={tail!r}"
            ) from error

    @classmethod
    def tearDownClass(cls):
        cls.stop_daemon()

    def check_mount(self, root):
        self.assertEqual(checker.run(root+"SKILL.md",None)["discovery"],"passed")
        self.assertEqual(checker.run(root+"SKILL.md",AUTH)["httpMcpParity"],"passed")
        _, manifest_url, manifest = checker.discover(root+"SKILL.md")
        for link in ("inventory",):
            checker.get_document(checker.url(manifest_url,manifest[link]))
        catalog_url = checker.url(manifest_url,manifest["discovery"]["catalog"])
        catalog = json.loads(checker.get_document(catalog_url))
        for item in catalog["skills"]:
            skill_url=checker.url(catalog_url,item["uri"])
            self.assertEqual(checker.url(skill_url,checker.manifest_ref(checker.get_document(skill_url))),manifest_url)
        mcp=checker.url(manifest_url,manifest["transports"]["mcp"]["endpoint"])
        for name,backend in [("agentlab_service_status",None),("agentlab_backend_catalog",None),("agentlab_backend_check","mock"),("agentlab_backend_check","missing"),("agentlab_backend_check","unavailable")]:
            cap=next(c for c in manifest["capabilities"] if c["id"]==name)
            args={} if backend is None else {"backend_id":backend}
            status,body=checker.curl(mcp,"POST",{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":name,"arguments":args}},AUTH,"2025-11-25")
            self.assertEqual(status,200)
            rpc=json.loads(body)["result"]
            hs,hb=checker.curl(checker.url(manifest_url,cap["http"]["path"].replace("{backend_id}",backend or "")),authorization=AUTH)
            value=json.loads(hb)
            self.assertEqual(rpc["structuredContent"],value if hs==200 else {"httpStatus":hs,"result":value})
            self.assertNotIn("127.0.0.1:9",body)
            CHECKS.append("mapping-parity")
        session = "ses_contract"
        task_cases = [
            ("agentlab_workspace_patch", {
                "sessionId":session,"operationKey":"acceptance-patch-1","baseRef":"revision-1",
                "patch":"*** Begin Patch\n*** Add File: hello.txt\n+hello\n*** End Patch\n","allowedPaths":["hello.txt"]
            }),
            ("agentlab_workspace_exec", {
                "sessionId":session,"operationKey":"acceptance-exec-1","baseRef":"revision-1",
                "command":"true","writablePaths":[],"commit":True
            }),
            ("agentlab_operation_get", {"sessionId":session,"operationKey":"acceptance-patch-1"}),
        ]
        for name,args in task_cases:
            cap=next(c for c in manifest["capabilities"] if c["id"]==name)
            status,body=checker.curl(mcp,"POST",{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":name,"arguments":args}},AUTH,"2025-11-25")
            self.assertEqual(status,200)
            rpc=json.loads(body)["result"]
            path=cap["http"]["path"].replace("{sessionId}",session).replace("{operationKey}",args["operationKey"])
            method=cap["http"]["method"]
            payload=args if method=="POST" else None
            hs,hb=checker.curl(checker.url(manifest_url,path),method,payload,AUTH)
            value=json.loads(hb)
            self.assertEqual(rpc["structuredContent"],value if hs==200 else {"httpStatus":hs,"result":value})
            self.assertEqual(rpc["isError"],hs!=200)
            CHECKS.append("task-degraded-parity")
        CHECKS.append("fresh-agent-mount")

    def test_direct_single_serial_proxies_and_relocated_manifest(self):
        self.check_mount(self.root)
        with proxy(self.root,"/one/") as (one,logs):
            self.check_mount(one)
            with proxy(one,"/edge/") as (two,logs2):
                self.check_mount(two)
            self.assertTrue(all(not auth for path,auth in logs if not "/api/" in path))
        with proxy(self.root,"/tenant/product/","relocated") as (relocated,logs):
            self.check_mount(relocated)
            self.assertTrue(any("a/b/custom-manifest.json" in path for path,_ in logs))

    def test_discovery_failure_and_cross_origin_never_forward_auth(self):
        with proxy(self.root,"/bad/","invalid") as (root,logs):
            with self.assertRaises(checker.ContractError):
                checker.run(root+"SKILL.md",AUTH)
            self.assertEqual(len(logs),1)
            self.assertFalse(logs[0][1])
        with proxy(self.root,"/cross/","cross-origin") as (root,logs):
            with self.assertRaisesRegex(checker.ContractError,"cross_origin"):
                checker.run(root+"SKILL.md",AUTH)
            self.assertTrue(all(not auth for _,auth in logs))

    def test_safe_yaml_and_uri_rejection(self):
        for newline in ("\n","\r\n"):
            self.assertEqual(checker.manifest_ref(newline.join(["---","metadata:",'  service-discovery-version: "1"','  service-manifest: "./custom/x.json"',"---"])),"./custom/x.json")
        bad=["none","---\nmetadata: {}\n---","---\nmetadata: !!python/object/apply:os.system ['secret']\n---","---\nmetadata: &x {service-discovery-version: '1', service-manifest: x}\na: *x\n---","---\nmetadata: {service-discovery-version: 1, service-manifest: x}\n---","---\nmetadata: {service-discovery-version: '2', service-manifest: x}\n---","---\nmetadata: {service-discovery-version: '1', service-manifest: x, service-manifest: y}\n---"]
        for raw in bad:
            with self.assertRaises(checker.ContractError):
                checker.manifest_ref(raw)
        for value in ("https://u:p@a/x","https://a/x?q=1","https://a/x#fragment","file:///tmp/x","https://a/\nsecret"):
            with self.assertRaises(checker.ContractError):
                checker.url(self.root,value)

if __name__ == "__main__":
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Acceptance))
    summary = {"schema":"agentlab.public_protocol_demo.v1", "ok":result.wasSuccessful(),
               "tests":result.testsRun,"mappingAndMountChecks":len(CHECKS),
               "scope":"published-chat-rs-http-mcp-website-skills",
               "storageConfigured":False,"writeSuccessQualified":False,
               "fullWhiteboxQualified":False,"fixedChannelPromoted":False,
               "failures":[{"test":str(test),"traceback":detail} for test,detail in result.failures + result.errors]}
    (EVIDENCE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))
    raise SystemExit(not result.wasSuccessful())
