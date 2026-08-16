from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html import escape
import hashlib
import hmac
import json
from pathlib import Path
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

from .config import settings
from .models import (
    FraudCase,
    FraudStatusUpdate,
    LowBalanceAlert,
    PaymentConfirmation,
    SosEnergyAdvance,
    SosEnergyRepayment,
    SubscriptionRequest,
    ValidationError,
)
from .security import verify_signature
from .services import SeegProtectService
from .sms import SmsGateway
from .storage import Storage


storage = Storage(settings.database_path)
service = SeegProtectService(settings, storage, SmsGateway(settings))
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MEROE_DASHBOARD = PROJECT_ROOT / "powerbi_meroe_v312" / "dashboard_meroe_v312.html"
MEROE_COLLABORATOR_DASHBOARD = (
    PROJECT_ROOT / "powerbi_meroe_v312" / "dashboard_collaborateur_v312.html"
)
MEROE_BACKGROUND = (
    PROJECT_ROOT
    / "powerbi_meroe_v312"
    / "assets"
    / "meroe_dashboard_background_v1.png"
)


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "SEEGProtectHTTP/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/health":
            self.send_json(
                200,
                {
                    "status": "ok",
                    "service": settings.app_name,
                    "version": settings.version,
                },
            )
            return

        if parsed.path in {"/meroe", "/meroe-v312"}:
            role = self.meroe_session_role()
            if not role:
                self.send_html(200, self.meroe_login_html(), cache="no-store")
                return
            dashboard = (
                MEROE_DASHBOARD if role == "owner" else MEROE_COLLABORATOR_DASHBOARD
            )
            if not dashboard.exists():
                self.send_json(404, {"error": "dashboard_not_found"})
                return
            self.send_html(200, dashboard.read_text(encoding="utf-8"), cache="no-store")
            return

        if parsed.path == "/meroe-logout":
            self.send_redirect(
                "/meroe-v312",
                "meroe_session=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict",
            )
            return

        if parsed.path == "/assets/meroe-dashboard-background.png":
            if not MEROE_BACKGROUND.exists():
                self.send_json(404, {"error": "asset_not_found"})
                return
            self.send_bytes(200, MEROE_BACKGROUND.read_bytes(), "image/png", cache=True)
            return

        if parsed.path == "/events":
            if not self.require_admin(query):
                return
            self.send_json(200, {"events": storage.recent_events(limit=self.query_limit(query, 20))})
            return

        if parsed.path == "/subscriptions":
            if not self.require_admin(query):
                return
            self.send_json(200, {"subscriptions": storage.list_subscriptions(self.query_limit(query, 50))})
            return

        if parsed.path == "/payments":
            if not self.require_admin(query):
                return
            self.send_json(200, {"payments": storage.list_payments(self.query_limit(query, 50))})
            return

        if parsed.path == "/notifications":
            if not self.require_admin(query):
                return
            self.send_json(200, {"notifications": storage.list_notifications(self.query_limit(query, 50))})
            return

        if parsed.path == "/fraud-cases":
            if not self.require_admin(query):
                return
            self.send_json(200, {"fraud_cases": storage.list_fraud_cases(self.query_limit(query, 50))})
            return

        if parsed.path == "/sos-energy":
            if not self.require_admin(query):
                return
            self.send_json(200, {"sos_energy": storage.list_sos_energy_advances(self.query_limit(query, 50))})
            return

        if parsed.path == "/meters":
            if not self.require_admin(query):
                return
            meter_id = self.query_value(query, "meter_id")
            if not meter_id:
                self.send_json(422, {"error": "validation_error", "message": "meter_id is required"})
                return
            detail = storage.meter_detail(meter_id, self.query_limit(query, 20))
            if not detail:
                self.send_json(404, {"error": "meter_not_found", "meter_id": meter_id})
                return
            self.send_json(200, {"meter": detail})
            return

        if parsed.path == "/meter":
            if not self.require_admin(query, html=True):
                return
            meter_id = self.query_value(query, "meter_id")
            self.send_html(200, self.meter_html(meter_id))
            return

        if parsed.path == "/architecture":
            if not self.require_admin(query, html=True):
                return
            self.send_html(200, self.architecture_html())
            return

        if parsed.path == "/process":
            if not self.require_admin(query, html=True):
                return
            self.send_html(200, self.process_html())
            return

        if parsed.path == "/roadmap":
            if not self.require_admin(query, html=True):
                return
            self.send_html(200, self.roadmap_html())
            return

        if parsed.path == "/dashboard":
            if not self.require_admin(query, html=True):
                return
            self.send_html(200, self.dashboard_html())
            return

        if parsed.path == "/dashboards":
            if not self.require_admin(query, html=True):
                return
            self.send_html(200, self.dashboards_html())
            return

        if parsed.path == "/":
            self.send_json(
                200,
                {
                    "service": settings.app_name,
                    "endpoints": [
                        "GET /health",
                        "GET /meroe-v312",
                        "GET /events?limit=20",
                        "GET /subscriptions?limit=50",
                        "GET /payments?limit=50",
                        "GET /notifications?limit=50",
                        "GET /fraud-cases?limit=50",
                        "GET /sos-energy?limit=50",
                        "GET /meters?meter_id=...",
                        "GET /meter?meter_id=...",
                        "GET /dashboards",
                        "GET /dashboard",
                        "GET /architecture",
                        "GET /process",
                        "GET /roadmap",
                        "POST /webhooks/subscriptions",
                        "POST /webhooks/payments",
                        "POST /webhooks/low-balance",
                        "POST /webhooks/fraud-cases",
                        "POST /webhooks/fraud-status",
                        "POST /webhooks/sos-energy",
                        "POST /webhooks/sos-energy-repayments",
                    ],
                },
            )
            return

        self.send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        raw_body = self.read_body()
        parsed = urlparse(self.path)
        if parsed.path == "/meroe-login":
            form = parse_qs(raw_body.decode("utf-8", errors="replace"))
            role = (form.get("role", [""])[0] or "").strip()
            password = form.get("password", [""])[0] or ""
            expected = {
                "owner": settings.meroe_owner_password,
                "collaborator": settings.meroe_collaborator_password,
            }.get(role, "")
            if expected and hmac.compare_digest(password, expected):
                cookie = (
                    f"meroe_session={self.create_meroe_session(role)}; Path=/; Max-Age=43200; "
                    "HttpOnly; Secure; SameSite=Strict"
                )
                self.send_redirect("/meroe-v312", cookie)
                return
            self.send_html(
                401,
                self.meroe_login_html("Identifiants incorrects."),
                cache="no-store",
            )
            return

        if not verify_signature(settings.webhook_secret, raw_body, self.headers.get("X-SEEG-Signature")):
            self.send_json(401, {"error": "invalid_signature"})
            return

        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
            if not isinstance(payload, dict):
                raise ValidationError("JSON body must be an object.")

            if parsed.path == "/webhooks/subscriptions":
                response = service.register_subscription(SubscriptionRequest.from_payload(payload))
                self.send_json(202, response)
                return

            if parsed.path == "/webhooks/payments":
                response = service.confirm_payment(PaymentConfirmation.from_payload(payload))
                self.send_json(202, response)
                return

            if parsed.path == "/webhooks/low-balance":
                response = service.handle_low_balance(LowBalanceAlert.from_payload(payload))
                self.send_json(202, response)
                return

            if parsed.path == "/webhooks/fraud-cases":
                response = service.register_fraud_case(FraudCase.from_payload(payload))
                self.send_json(202, response)
                return

            if parsed.path == "/webhooks/fraud-status":
                response = service.update_fraud_status(FraudStatusUpdate.from_payload(payload))
                self.send_json(202, response)
                return

            if parsed.path == "/webhooks/sos-energy":
                response = service.request_sos_energy(SosEnergyAdvance.from_payload(payload))
                self.send_json(202, response)
                return

            if parsed.path == "/webhooks/sos-energy-repayments":
                response = service.repay_sos_energy(SosEnergyRepayment.from_payload(payload))
                self.send_json(202, response)
                return

            self.send_json(404, {"error": "not_found"})
        except json.JSONDecodeError:
            self.send_json(400, {"error": "invalid_json"})
        except ValidationError as exc:
            self.send_json(422, {"error": "validation_error", "message": str(exc)})

    def read_body(self) -> bytes:
        content_length = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(content_length)

    def send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, status_code: int, html: str, cache: str | None = None) -> None:
        body = html.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if cache:
            self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def send_redirect(self, location: str, cookie: str | None = None) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    @staticmethod
    def create_meroe_session(role: str, now: int | None = None) -> str:
        expires = (int(time.time()) if now is None else now) + 43200
        payload = f"{role}.{expires}"
        signature = hmac.new(
            settings.webhook_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return f"{payload}.{signature}"

    def meroe_session_role(self, now: int | None = None) -> str | None:
        cookies = self.headers.get("Cookie", "")
        token = next(
            (part.split("=", 1)[1] for part in cookies.split(";") if part.strip().startswith("meroe_session=")),
            "",
        )
        try:
            role, expires_text, signature = token.strip().split(".", 2)
            expires = int(expires_text)
        except (ValueError, TypeError):
            return None
        if role not in {"owner", "collaborator"} or expires < (int(time.time()) if now is None else now):
            return None
        payload = f"{role}.{expires}"
        expected = hmac.new(
            settings.webhook_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return role if hmac.compare_digest(signature, expected) else None

    @staticmethod
    def meroe_login_html(error: str = "") -> str:
        alert = f'<div class="error">{escape(error)}</div>' if error else ""
        return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Connexion MÉROÉ</title><style>
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;color:#f4f7fa;font:14px Segoe UI,sans-serif;background:#06111c url('/assets/meroe-dashboard-background.png') center/cover}}body:before{{content:'';position:fixed;inset:0;background:rgba(3,13,22,.72);z-index:-1}}.box{{width:min(430px,92vw);padding:32px;border:1px solid #315467;border-radius:22px;background:rgba(8,28,42,.92);box-shadow:0 25px 70px #0008;backdrop-filter:blur(18px)}}.mark{{width:52px;height:52px;display:grid;place-items:center;border-radius:16px;background:linear-gradient(145deg,#20d6b5,#5b8cff);font-weight:900;font-size:20px}}h1{{margin:20px 0 6px}}p{{color:#9db0be}}label{{display:block;margin:20px 0 7px;color:#c8d5de}}select,input{{width:100%;padding:13px;border-radius:10px;border:1px solid #315467;background:#0d293b;color:white}}button{{width:100%;margin-top:24px;padding:13px;border:0;border-radius:10px;background:linear-gradient(90deg,#20d6b5,#5b8cff);font-weight:800;color:#06111c;cursor:pointer}}.error{{margin-top:15px;padding:10px;border-radius:8px;color:#ff8b8b;background:#ff6b6b18}}small{{display:block;margin-top:18px;color:#71899a}}</style></head><body><form class="box" method="post" action="/meroe-login"><div class="mark">M</div><h1>MÉROÉ Control Center</h1><p>Accès sécurisé selon votre niveau d’autorisation.</p>{alert}<label>Profil</label><select name="role" required><option value="collaborator">Collaborateur opérationnel</option><option value="owner">Propriétaire — accès complet</option></select><label>Mot de passe</label><input type="password" name="password" autocomplete="current-password" required><button type="submit">Se connecter</button><small>Session sécurisée de 12 heures · Aucune donnée nominative</small></form></body></html>"""

    def send_bytes(
        self, status_code: int, body: bytes, content_type: str, cache: bool = False
    ) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if cache:
            self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def query_limit(query: dict[str, list[str]], default: int) -> int:
        try:
            value = int(query.get("limit", [str(default)])[0])
        except ValueError:
            value = default
        return max(1, min(value, 100))

    @staticmethod
    def query_value(query: dict[str, list[str]], name: str) -> str:
        return (query.get(name, [""])[0] or "").strip()

    def require_admin(self, query: dict[str, list[str]], html: bool = False) -> bool:
        if not settings.admin_token:
            return True

        token = self.headers.get("X-Admin-Token") or self.query_value(query, "token")
        if hmac.compare_digest(token, settings.admin_token):
            return True

        if html:
            self.send_html(401, self.login_html())
        else:
            self.send_json(401, {"error": "admin_auth_required"})
        return False

    @staticmethod
    def auth_query() -> str:
        return f"?token={settings.admin_token}" if settings.admin_token else ""

    def admin_link(self, path: str) -> str:
        if not settings.admin_token:
            return path
        separator = "&" if "?" in path else "?"
        return f"{path}{separator}token={settings.admin_token}"

    def login_html(self) -> str:
        return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(settings.app_name)} - Acces admin</title>
  <style>
    body {{ font-family:"Segoe UI", Arial, sans-serif; margin:0; background:#f4f7f8; color:#142126; display:grid; min-height:100vh; place-items:center; }}
    .panel {{ width:min(460px, calc(100vw - 32px)); background:white; border:1px solid #d8e1e4; border-radius:8px; padding:22px; box-shadow:0 10px 28px rgba(20,33,38,.08); }}
    h1 {{ margin:0 0 8px; font-size:24px; }}
    p {{ color:#68767d; }}
    form {{ display:flex; gap:8px; margin-top:16px; }}
    input {{ flex:1; padding:10px; border:1px solid #b7c5c9; border-radius:6px; }}
    button {{ padding:10px 14px; border:0; border-radius:6px; background:#0b6b4f; color:white; font-weight:650; }}
  </style>
</head>
<body>
  <section class="panel">
    <h1>Acces admin</h1>
    <p>Entre le token admin pour consulter les donnees SEEG Protect.</p>
    <form method="get">
      <input name="token" type="password" placeholder="Token admin" required>
      <button type="submit">Entrer</button>
    </form>
  </section>
</body>
</html>"""

    def dashboard_html(self) -> str:
        summary = storage.dashboard_summary()
        metrics = storage.dashboard_metrics()
        subscriptions = storage.list_subscriptions(10)
        notifications = storage.list_notifications(10)
        fraud_cases = storage.list_fraud_cases(10)
        sos_energy = storage.list_sos_energy_advances(10)
        events = storage.recent_events(10)
        return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(settings.app_name)} - Tableau de bord</title>
  <style>
    :root {{ --ink:#142126; --muted:#68767d; --line:#d8e1e4; --soft:#f4f7f8; --panel:#ffffff; --brand:#0b6b4f; --brand2:#15936b; --warn:#c47a00; --bad:#b23b3b; }}
    * {{ box-sizing: border-box; }}
    body {{ font-family: "Segoe UI", Arial, sans-serif; margin: 0; color: var(--ink); background: var(--soft); }}
    header {{ background: linear-gradient(135deg, #0b6b4f, #173f49); color: white; padding: 22px 28px; }}
    main {{ padding: 22px 28px 34px; max-width: 1240px; margin: 0 auto; }}
    h1 {{ font-size: 28px; margin: 0 0 6px; letter-spacing: 0; }}
    h2 {{ font-size: 18px; margin: 0 0 12px; }}
    p {{ color: var(--muted); }}
    nav {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:16px; }}
    nav a, .button {{ color:white; background:rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.25); padding:8px 11px; border-radius:6px; text-decoration:none; font-size:14px; }}
    .grid {{ display:grid; grid-template-columns: repeat(12, 1fr); gap:16px; }}
    .stats {{ margin: 20px 0; }}
    .stat, .panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; box-shadow: 0 8px 20px rgba(20,33,38,.04); }}
    .span-3 {{ grid-column: span 3; }}
    .span-4 {{ grid-column: span 4; }}
    .span-6 {{ grid-column: span 6; }}
    .span-12 {{ grid-column: span 12; }}
    .label {{ color: var(--muted); font-size: 13px; }}
    .value {{ font-size: 30px; font-weight: 750; margin-top: 6px; }}
    .subtle {{ color: var(--muted); font-size:13px; margin-top:8px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid var(--line); border-radius: 8px; overflow:hidden; }}
    th, td {{ text-align: left; border-bottom: 1px solid #e8eef0; padding: 10px; font-size: 13px; vertical-align: top; }}
    th {{ background: #eef5f3; color: #263238; font-weight: 650; }}
    tr:last-child td {{ border-bottom: 0; }}
    a {{ color: var(--brand); }}
    form {{ display: flex; gap: 8px; margin: 0; flex-wrap: wrap; }}
    input {{ padding: 10px; border: 1px solid #b7c5c9; border-radius: 6px; min-width: 280px; }}
    button {{ padding: 10px 14px; border: 0; border-radius: 6px; background: var(--brand); color: white; cursor: pointer; font-weight:650; }}
    .bar-row {{ display:grid; grid-template-columns: 150px 1fr 44px; gap: 10px; align-items:center; margin: 10px 0; }}
    .bar-track {{ height: 12px; background:#e7edef; border-radius:999px; overflow:hidden; }}
    .bar-fill {{ height:100%; background: linear-gradient(90deg, var(--brand2), var(--brand)); border-radius:999px; }}
    .timeline {{ display:flex; gap:8px; align-items:end; height:150px; padding-top:10px; }}
    .day {{ flex:1; display:flex; flex-direction:column; align-items:center; gap:8px; }}
    .day-bar {{ width:100%; max-width:42px; min-height:3px; background:linear-gradient(180deg, #24a47a, #0b6b4f); border-radius:6px 6px 0 0; }}
    .day-label {{ font-size:11px; color:var(--muted); }}
    .status-pill {{ display:inline-block; padding:4px 8px; border-radius:999px; background:#e9f5ef; color:#0b6b4f; font-weight:650; }}
    @media (max-width: 850px) {{ .span-3, .span-4, .span-6 {{ grid-column: span 12; }} main {{ padding:16px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(settings.app_name)}</h1>
    <div>Supervision des abonnements, paiements, alertes et notifications SMS.</div>
    <nav>
      <a href="{self.admin_link("/dashboard")}">Tableau de bord</a>
      <a href="{self.admin_link("/architecture")}">Architecture</a>
      <a href="{self.admin_link("/roadmap")}">Suivi projet</a>
      <a href="{self.admin_link("/subscriptions?limit=20")}">Souscriptions JSON</a>
      <a href="{self.admin_link("/notifications?limit=20")}">Notifications JSON</a>
    </nav>
  </header>
  <main>
    <section class="grid stats">
      {self.stat_html("Souscriptions", summary["subscriptions"])}
      {self.stat_html("Actives", summary["active_subscriptions"])}
      {self.stat_html("Paiements", summary["payments"])}
      {self.stat_html("SMS/notifications", summary["notifications"])}
      {self.stat_html("Dossiers fraude", summary["fraud_cases"])}
      {self.stat_html("Recouvre fraude", f'{summary["fraud_collected_xaf"]:,} FCFA'.replace(",", " "))}
      {self.stat_html("Fee MEROE", f'{summary["fraud_success_fee_xaf"]:,} FCFA'.replace(",", " "))}
      {self.stat_html("SOS Energie", summary["sos_energy_advances"])}
      {self.stat_html("Marge SOS", f'{summary["sos_energy_margin_xaf"]:,} FCFA'.replace(",", " "))}
    </section>
    <section class="grid">
      <div class="panel span-6">
        <h2>Recherche compteur</h2>
        <form action="/meter" method="get">
          {self.hidden_token_input()}
          <input name="meter_id" placeholder="Exemple : api-meter-1782848694" required>
          <button type="submit">Ouvrir la fiche</button>
        </form>
        <div class="subtle">La fiche compteur regroupe abonnement, paiement, SMS et evenements techniques.</div>
      </div>
      <div class="panel span-6">
        <h2>Statut des abonnements</h2>
        {self.bar_chart_html(metrics["subscription_statuses"], "status")}
      </div>
      <div class="panel span-6">
        <h2>SMS par jour</h2>
        {self.timeline_html(metrics["notification_days"])}
      </div>
      <div class="panel span-6">
        <h2>Statut des SMS</h2>
        {self.donut_chart_html(metrics["notification_statuses"])}
      </div>
      <div class="panel span-6">
        <h2>Evenements techniques</h2>
        {self.bar_chart_html(metrics["event_types"], "event_type")}
      </div>
      <div class="panel span-6">
        <h2>Statuts fraude</h2>
        {self.bar_chart_html(metrics["fraud_statuses"], "status")}
      </div>
      <div class="panel span-6">
        <h2>Codes fraude</h2>
        {self.bar_chart_html(metrics["fraud_codes"], "fraud_code")}
      </div>
      <div class="panel span-6">
        <h2>SOS Energie</h2>
        {self.bar_chart_html(metrics["sos_statuses"], "status")}
      </div>
      <div class="panel span-6">
        <h2>Avancement mise en ligne</h2>
        {self.progress_html("MVP fonctionnel", 100)}
        {self.progress_html("Dashboard partenaire", 85)}
        {self.progress_html("Securite admin", 75)}
        {self.progress_html("SMS reel fournisseur", 35)}
        <div class="subtle">Voir le detail dans la page Suivi projet.</div>
      </div>
      <div class="panel span-12">
        <h2>Dernieres souscriptions</h2>
        {self.table_html(subscriptions, ["subscription_id", "meter_id", "phone_number", "status", "created_at"])}
      </div>
      <div class="panel span-12">
        <h2>Derniers SMS</h2>
        {self.table_html(notifications, ["meter_id", "phone_number", "status", "message", "created_at"])}
      </div>
      <div class="panel span-12">
        <h2>Dossiers fraude MEROE V6.4</h2>
        {self.table_html(fraud_cases, ["fraud_case_id", "meter_id", "score_fraud", "fraud_code", "meter_status", "collected_amount_xaf", "success_fee_xaf", "audit_flag", "updated_at"])}
      </div>
      <div class="panel span-12">
        <h2>SOS Energie</h2>
        {self.table_html(sos_energy, ["advance_id", "meter_id", "amount_advanced_xaf", "amount_due_xaf", "amount_paid_xaf", "margin_xaf", "status", "due_at", "paid_at"])}
      </div>
      <div class="panel span-12">
        <h2>Journal technique recent</h2>
        {self.table_html(events, ["event_type", "reference", "created_at"])}
      </div>
    </section>
  </main>
</body>
</html>"""

    def meter_html(self, meter_id: str) -> str:
        if not meter_id:
            content = "<p>Renseigne un identifiant compteur depuis le tableau de bord.</p>"
        else:
            detail = storage.meter_detail(meter_id, 50)
            if not detail:
                content = f"<p>Compteur introuvable : <strong>{escape(meter_id)}</strong></p>"
            else:
                subscription = detail["subscription"]
                content = f"""
    <section class="stats">
      {self.stat_html("Statut", str(subscription["status"]))}
      {self.stat_html("Paiements", len(detail["payments"]))}
      {self.stat_html("SMS", len(detail["notifications"]))}
      {self.stat_html("Evenements", len(detail["events"]))}
    </section>
    <h2>Abonnement</h2>
    {self.table_html([subscription], ["subscription_id", "meter_id", "phone_number", "customer_ref", "status", "created_at", "activated_at"])}
    <h2>Paiements</h2>
    {self.table_html(detail["payments"], ["transaction_id", "amount_xaf", "status", "paid_at", "created_at"])}
    <h2>SMS et notifications</h2>
    {self.table_html(detail["notifications"], ["phone_number", "channel", "status", "message", "created_at"])}
    <h2>Evenements compteur</h2>
    {self.table_html(detail["events"], ["event_type", "reference", "created_at"])}
"""

        return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(settings.app_name)} Compteur</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; color: #172026; background: #f5f7f8; }}
    header {{ background: #0b6b4f; color: white; padding: 18px 24px; }}
    main {{ padding: 20px 24px; max-width: 1180px; margin: 0 auto; }}
    h1 {{ font-size: 24px; margin: 0; }}
    h2 {{ font-size: 18px; margin: 24px 0 10px; }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }}
    .stat {{ background: white; border: 1px solid #dbe3e5; border-radius: 6px; padding: 14px; }}
    .label {{ color: #5d6b72; font-size: 13px; }}
    .value {{ font-size: 24px; font-weight: 700; margin-top: 6px; overflow-wrap: anywhere; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dbe3e5; }}
    th, td {{ text-align: left; border-bottom: 1px solid #e7ecee; padding: 9px; font-size: 13px; vertical-align: top; }}
    th {{ background: #eef3f1; color: #263238; }}
    a {{ color: #0b6b4f; }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(settings.app_name)} - Compteur {escape(meter_id or "")}</h1>
  </header>
  <main>
    <p><a href="{self.admin_link("/dashboard")}">Retour au tableau de bord</a></p>
    {content}
  </main>
</body>
</html>"""

    def dashboards_html(self) -> str:
        summary = storage.dashboard_summary()
        return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(settings.app_name)} - Portail partenaires</title>
  <style>
    :root {{ --ink:#142126; --muted:#68767d; --line:#d8e1e4; --soft:#f4f7f8; --panel:#fff; --brand:#0b6b4f; --brand2:#173f49; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--soft); color:var(--ink); font-family:"Segoe UI", Arial, sans-serif; }}
    header {{ background:linear-gradient(135deg, #0b6b4f, #173f49); color:white; padding:30px; }}
    main {{ max-width:1180px; margin:0 auto; padding:24px 30px 40px; }}
    h1 {{ margin:0 0 8px; font-size:32px; letter-spacing:0; }}
    h2 {{ margin:0 0 10px; font-size:18px; }}
    p {{ color:var(--muted); }}
    .lead {{ color:rgba(255,255,255,.84); max-width:760px; }}
    .grid {{ display:grid; grid-template-columns:repeat(12, 1fr); gap:16px; }}
    .card {{ grid-column:span 6; background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:18px; box-shadow:0 8px 20px rgba(20,33,38,.05); }}
    .kpi {{ grid-column:span 3; background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; }}
    .value {{ font-size:30px; font-weight:800; color:var(--brand); margin-top:6px; }}
    .button {{ display:inline-block; margin-top:10px; padding:10px 13px; border-radius:6px; background:var(--brand); color:white; text-decoration:none; font-weight:700; }}
    .secondary {{ background:#eef5f3; color:var(--brand); }}
    .label {{ color:var(--muted); font-size:13px; }}
    .toplinks {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:18px; }}
    .toplinks a {{ color:white; background:rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.25); padding:8px 11px; border-radius:6px; text-decoration:none; font-size:14px; }}
    @media (max-width:850px) {{ .card,.kpi {{ grid-column:span 12; }} main {{ padding:16px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Portail partenaires</h1>
    <div class="lead">Acces centralise aux tableaux de bord, au suivi projet, a l'architecture et aux fiches compteurs SEEG Protect.</div>
    <div class="toplinks">
      <a href="{self.admin_link('/dashboard')}">Dashboard operationnel</a>
      <a href="{self.admin_link('/roadmap')}">Suivi projet</a>
      <a href="{self.admin_link('/architecture')}">Architecture</a>
      <a href="{self.admin_link('/process')}">Processus complet</a>
    </div>
  </header>
  <main>
    <section class="grid">
      <div class="kpi"><div class="label">Souscriptions</div><div class="value">{summary["subscriptions"]}</div></div>
      <div class="kpi"><div class="label">Actives</div><div class="value">{summary["active_subscriptions"]}</div></div>
      <div class="kpi"><div class="label">Paiements</div><div class="value">{summary["payments"]}</div></div>
      <div class="kpi"><div class="label">SMS</div><div class="value">{summary["notifications"]}</div></div>

      <article class="card">
        <h2>Dashboard operationnel</h2>
        <p>KPIs, graphiques, SMS par jour, statuts, souscriptions recentes et journal technique.</p>
        <a class="button" href="{self.admin_link('/dashboard')}">Ouvrir</a>
      </article>
      <article class="card">
        <h2>Suivi projet partenaire</h2>
        <p>Avancement, lots de mise en ligne, decisions restantes et preuve de demonstration.</p>
        <a class="button" href="{self.admin_link('/roadmap')}">Ouvrir</a>
      </article>
      <article class="card">
        <h2>Architecture fonctionnelle</h2>
        <p>Scenario metier, schema technique et explication des flux HTTP, stockage et SMS.</p>
        <a class="button" href="{self.admin_link('/architecture')}">Ouvrir</a>
      </article>
      <article class="card">
        <h2>Processus complet</h2>
        <p>Vue de bout en bout : client, SEEG, API, simulation locale, fraude MEROE, dashboard et remplacement par les vraies donnees.</p>
        <a class="button" href="{self.admin_link('/process')}">Ouvrir</a>
      </article>
      <article class="card">
        <h2>Fiche compteur</h2>
        <p>Recherche detaillee d'un compteur : abonnement, paiement, SMS et historique technique.</p>
        <a class="button secondary" href="{self.admin_link('/dashboard')}">Rechercher depuis le dashboard</a>
      </article>
    </section>
  </main>
</body>
</html>"""

    def process_html(self) -> str:
        summary = storage.dashboard_summary()
        fraud_cases = storage.list_fraud_cases(6)
        sos_energy = storage.list_sos_energy_advances(6)
        return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(settings.app_name)} - Processus complet</title>
  <style>
    :root {{ --ink:#142126; --muted:#68767d; --line:#d8e1e4; --soft:#f4f7f8; --panel:#fff; --brand:#0b6b4f; --blue:#256f9c; --amber:#b86f00; --bad:#a33a3a; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--soft); color:var(--ink); font-family:"Segoe UI", Arial, sans-serif; }}
    header {{ background:linear-gradient(135deg, #173f49, #0b6b4f); color:white; padding:26px 30px; }}
    main {{ max-width:1240px; margin:0 auto; padding:24px 30px 42px; }}
    h1 {{ margin:0 0 8px; font-size:31px; letter-spacing:0; }}
    h2 {{ margin:0 0 12px; font-size:19px; }}
    h3 {{ margin:0 0 8px; font-size:15px; color:#173f49; }}
    p {{ color:var(--muted); }}
    nav {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:16px; }}
    nav a, .button {{ color:white; background:rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.25); padding:8px 11px; border-radius:6px; text-decoration:none; font-size:14px; }}
    a {{ color:var(--brand); }}
    .grid {{ display:grid; grid-template-columns:repeat(12, 1fr); gap:16px; }}
    .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:17px; box-shadow:0 8px 20px rgba(20,33,38,.04); }}
    .span-3 {{ grid-column:span 3; }}
    .span-4 {{ grid-column:span 4; }}
    .span-6 {{ grid-column:span 6; }}
    .span-12 {{ grid-column:span 12; }}
    .kpi {{ font-size:28px; font-weight:800; color:var(--brand); margin-top:4px; overflow-wrap:anywhere; }}
    .label {{ color:var(--muted); font-size:13px; }}
    .flow {{ display:grid; grid-template-columns:repeat(7, minmax(120px, 1fr)); gap:10px; align-items:stretch; }}
    .node {{ border:1px solid var(--line); border-top:5px solid var(--brand); border-radius:8px; background:#fbfdfd; padding:12px; min-height:142px; }}
    .node strong {{ display:block; margin-bottom:7px; color:var(--ink); }}
    .node small {{ display:block; color:var(--muted); line-height:1.35; }}
    .node.sim {{ border-top-color:var(--amber); }}
    .node.fraud {{ border-top-color:var(--blue); }}
    .node.cash {{ border-top-color:#168157; }}
    .step {{ display:grid; grid-template-columns:44px 1fr; gap:12px; padding:13px 0; border-bottom:1px solid #e7edef; }}
    .step:last-child {{ border-bottom:0; }}
    .num {{ width:34px; height:34px; border-radius:999px; display:grid; place-items:center; background:#e9f5ef; color:var(--brand); font-weight:800; }}
    code {{ background:#eef5f3; padding:2px 5px; border-radius:4px; }}
    table {{ width:100%; border-collapse:collapse; }}
    th, td {{ text-align:left; border-bottom:1px solid #e7edef; padding:9px; font-size:13px; vertical-align:top; }}
    th {{ background:#eef5f3; color:#173f49; }}
    @media (max-width:1050px) {{ .flow {{ grid-template-columns:1fr 1fr; }} .span-3,.span-4,.span-6 {{ grid-column:span 12; }} }}
    @media (max-width:680px) {{ main {{ padding:16px; }} .flow {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Processus complet SEEG Protect / MEROE</h1>
    <div>Vue de bout en bout : client, SEEG, API, simulation locale, fraude, cash et dashboard.</div>
    <nav>
      <a href="{self.admin_link('/dashboards')}">Portail</a>
      <a href="{self.admin_link('/dashboard')}">Dashboard</a>
      <a href="{self.admin_link('/architecture')}">Architecture technique</a>
      <a href="{self.admin_link('/fraud-cases?limit=20')}">Dossiers fraude JSON</a>
    </nav>
  </header>
  <main>
    <section class="grid">
      <div class="panel span-3"><div class="label">Souscriptions</div><div class="kpi">{summary["subscriptions"]}</div></div>
      <div class="panel span-3"><div class="label">SMS</div><div class="kpi">{summary["notifications"]}</div></div>
      <div class="panel span-3"><div class="label">Dossiers fraude</div><div class="kpi">{summary["fraud_cases"]}</div></div>
      <div class="panel span-3"><div class="label">Fee MEROE</div><div class="kpi">{f'{summary["fraud_success_fee_xaf"]:,}'.replace(",", " ")} FCFA</div></div>
      <div class="panel span-3"><div class="label">SOS Energie</div><div class="kpi">{summary["sos_energy_advances"]}</div></div>
      <div class="panel span-3"><div class="label">Marge SOS</div><div class="kpi">{f'{summary["sos_energy_margin_xaf"]:,}'.replace(",", " ")} FCFA</div></div>

      <section class="panel span-12">
        <h2>Le film complet</h2>
        <div class="flow">
          <div class="node"><strong>1. Client</strong><small>Possede un compteur EDAN prepaid. Il recoit une alerte SMS quand le solde devient faible.</small></div>
          <div class="node"><strong>2. SEEG / EDAN</strong><small>Produit les donnees : souscription, paiement, solde, logs compteur, statut COUPE ou REACTIVE.</small></div>
          <div class="node"><strong>3. Webhooks</strong><small>La SEEG pousse les evenements vers l'API avec une signature HMAC.</small></div>
          <div class="node"><strong>4. API</strong><small>Valide le JSON, applique la logique metier, stocke les informations dans SQLite.</small></div>
          <div class="node sim"><strong>5. Simulation locale</strong><small>Remplace provisoirement EDAN avec de faux compteurs et de faux dossiers fraude.</small></div>
          <div class="node fraud"><strong>6. SOS Energie</strong><small>Avance 2 000 FCFA au client et attend 2 400 FCFA a J+3.</small></div>
          <div class="node fraud"><strong>7. MEROE Fraude</strong><small>Transforme les signaux EDAN en Liste Rouge, score, statut et montant recouvrable.</small></div>
          <div class="node cash"><strong>8. Dashboard</strong><small>Montre les KPI DAF/DSI : SMS, SOS, fraude, recouvrement, fee, audit.</small></div>
        </div>
      </section>

      <section class="panel span-12">
        <h2>Ordre chronologique du systeme</h2>
        <div class="step"><div class="num">1</div><div><h3>Le client a un compteur EDAN</h3><p>Le compteur produit les donnees de base : solde, consommation, evenements et statut.</p></div></div>
        <div class="step"><div class="num">2</div><div><h3>Le client souscrit a SEEG Protect</h3><p>La SEEG appelle <code>POST /webhooks/subscriptions</code>.</p></div></div>
        <div class="step"><div class="num">3</div><div><h3>Le paiement active le service</h3><p>La SEEG appelle <code>POST /webhooks/payments</code>. Le compteur devient eligible aux alertes.</p></div></div>
        <div class="step"><div class="num">4</div><div><h3>Le solde faible declenche une alerte</h3><p>La SEEG appelle <code>POST /webhooks/low-balance</code>. Le systeme calcule les jours restants.</p></div></div>
        <div class="step"><div class="num">5</div><div><h3>Le client recoit le SMS</h3><p>En demo, le SMS est simule. En production, il part via le fournisseur SMS.</p></div></div>
        <div class="step"><div class="num">6</div><div><h3>SOS Energie peut etre propose</h3><p>Si le client est eligible, MEROE avance <code>2 000 FCFA</code> d'energie et attend <code>2 400 FCFA</code> a J+3.</p></div></div>
        <div class="step"><div class="num">7</div><div><h3>Le remboursement SOS est suivi</h3><p>Webhook <code>POST /webhooks/sos-energy-repayments</code>. La marge attendue est <code>400 FCFA</code>.</p></div></div>
        <div class="step"><div class="num">8</div><div><h3>MEROE scanne les signaux fraude</h3><p>Logs EDAN, tamper, tension, 0 kWh et statuts produisent une Liste Rouge.</p></div></div>
        <div class="step"><div class="num">9</div><div><h3>La SEEG traite la Liste Rouge</h3><p>Agent, huissier, coupure, PV et statut compteur.</p></div></div>
        <div class="step"><div class="num">10</div><div><h3>Le recouvrement cree la fee MEROE</h3><p>Si la SEEG encaisse, MEROE calcule la success fee fraude de 5% et affiche le resultat au dashboard.</p></div></div>
      </section>

      <section class="panel span-6">
        <h2>Processus protection client</h2>
        <div class="step"><div class="num">1</div><div><h3>Souscription</h3><p>Webhook <code>POST /webhooks/subscriptions</code>. Le compteur passe en attente de paiement.</p></div></div>
        <div class="step"><div class="num">2</div><div><h3>Paiement</h3><p>Webhook <code>POST /webhooks/payments</code>. L'abonnement devient actif.</p></div></div>
        <div class="step"><div class="num">3</div><div><h3>Alerte solde faible</h3><p>Webhook <code>POST /webhooks/low-balance</code>. Le service calcule les jours restants.</p></div></div>
        <div class="step"><div class="num">4</div><div><h3>SMS</h3><p>En demo, le SMS va dans <code>logs/sms_outbox.jsonl</code>. En production, il part chez le fournisseur SMS.</p></div></div>
      </section>

      <section class="panel span-6">
        <h2>Processus fraude MEROE</h2>
        <div class="step"><div class="num">1</div><div><h3>Detection</h3><p>Webhook <code>POST /webhooks/fraud-cases</code>. MEROE recoit le score et le code fraude.</p></div></div>
        <div class="step"><div class="num">2</div><div><h3>Terrain SEEG</h3><p>Agent et huissier traitent la Liste Rouge : constat, coupure, PV.</p></div></div>
        <div class="step"><div class="num">3</div><div><h3>Statut compteur</h3><p>Webhook <code>POST /webhooks/fraud-status</code>. Le statut devient <code>COUPE</code> ou <code>REACTIVE</code>.</p></div></div>
        <div class="step"><div class="num">4</div><div><h3>Cash</h3><p>Si la SEEG encaisse, MEROE calcule 5% de success fee. Si motif suspect, le dossier passe en audit.</p></div></div>
      </section>

      <section class="panel span-6">
        <h2>Processus SOS Energie</h2>
        <div class="step"><div class="num">1</div><div><h3>Client eligible</h3><p>Score Orange ou solde faible : le client peut demander une avance.</p></div></div>
        <div class="step"><div class="num">2</div><div><h3>Avance</h3><p>Webhook <code>POST /webhooks/sos-energy</code>. MEROE avance <code>2 000 FCFA</code>.</p></div></div>
        <div class="step"><div class="num">3</div><div><h3>Remboursement</h3><p>Webhook <code>POST /webhooks/sos-energy-repayments</code>. Le client rembourse <code>2 400 FCFA</code> a J+3.</p></div></div>
        <div class="step"><div class="num">4</div><div><h3>Marge</h3><p>MEROE conserve <code>400 FCFA</code> de marge sur le dossier rembourse.</p></div></div>
      </section>

      <section class="panel span-6">
        <h2>Simulation locale</h2>
        <p>La simulation sert a voir l'application fonctionner avant les vraies donnees EDAN.</p>
        <p><code>python scripts\\demo_fraud_data.py</code></p>
        <p>Elle cree des compteurs fictifs, des SMS, des dossiers Liste Rouge, des statuts <code>COUPE</code>/<code>REACTIVE</code>, du recouvrement et une alerte audit.</p>
      </section>

      <section class="panel span-6">
        <h2>Remplacement par les vraies donnees</h2>
        <p>Quand la SEEG donne les vrais fichiers ou webhooks EDAN, on remplace seulement la source de donnees. Le dashboard, la base, les endpoints et les calculs restent les memes.</p>
        <p>La logique cible : <code>Simulation locale -> donnees pilote EDAN -> API production SEEG</code>.</p>
      </section>

      <section class="panel span-12">
        <h2>Dossiers fraude actuellement visibles</h2>
        {self.table_html(fraud_cases, ["fraud_case_id", "meter_id", "score_fraud", "fraud_code", "meter_status", "reactivation_reason", "collected_amount_xaf", "success_fee_xaf", "audit_flag"])}
      </section>
      <section class="panel span-12">
        <h2>SOS Energie actuellement visible</h2>
        {self.table_html(sos_energy, ["advance_id", "meter_id", "amount_advanced_xaf", "amount_due_xaf", "amount_paid_xaf", "margin_xaf", "status", "due_at", "paid_at"])}
      </section>
    </section>
  </main>
</body>
</html>"""

    def roadmap_html(self) -> str:
        return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(settings.app_name)} - Suivi projet</title>
  <style>
    :root {{ --ink:#142126; --muted:#68767d; --line:#d8e1e4; --soft:#f4f7f8; --panel:#fff; --brand:#0b6b4f; --amber:#c47a00; --blue:#256f9c; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--soft); color:var(--ink); font-family:"Segoe UI", Arial, sans-serif; }}
    header {{ background:linear-gradient(135deg, #173f49, #0b6b4f); color:white; padding:24px 30px; }}
    main {{ max-width:1220px; margin:0 auto; padding:24px 30px 38px; }}
    h1 {{ margin:0 0 6px; font-size:30px; letter-spacing:0; }}
    h2 {{ margin:0 0 12px; font-size:18px; }}
    h3 {{ margin:0 0 8px; font-size:15px; color:#173f49; }}
    p {{ color:var(--muted); }}
    a {{ color:var(--brand); }}
    nav {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:16px; }}
    nav a {{ color:white; background:rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.25); padding:8px 11px; border-radius:6px; text-decoration:none; font-size:14px; }}
    .grid {{ display:grid; grid-template-columns:repeat(12, 1fr); gap:16px; }}
    .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:17px; box-shadow:0 8px 20px rgba(20,33,38,.04); }}
    .span-3 {{ grid-column:span 3; }}
    .span-4 {{ grid-column:span 4; }}
    .span-6 {{ grid-column:span 6; }}
    .span-12 {{ grid-column:span 12; }}
    .kpi {{ font-size:28px; font-weight:800; color:var(--brand); margin-top:5px; }}
    .tag {{ display:inline-block; padding:4px 8px; border-radius:999px; background:#e9f5ef; color:#0b6b4f; font-weight:700; font-size:12px; }}
    .timeline {{ position:relative; margin-top:8px; }}
    .item {{ display:grid; grid-template-columns:110px 1fr; gap:14px; padding:12px 0; border-bottom:1px solid #e7edef; }}
    .item:last-child {{ border-bottom:0; }}
    .date {{ font-weight:750; color:var(--brand); }}
    .bar {{ height:10px; background:#e7edef; border-radius:999px; overflow:hidden; margin:8px 0 3px; }}
    .fill {{ height:100%; background:linear-gradient(90deg, #24a47a, #0b6b4f); }}
    table {{ width:100%; border-collapse:collapse; }}
    th, td {{ text-align:left; border-bottom:1px solid #e7edef; padding:10px; font-size:13px; vertical-align:top; }}
    th {{ background:#eef5f3; color:#173f49; }}
    @media (max-width:850px) {{ .span-3,.span-4,.span-6 {{ grid-column:span 12; }} main {{ padding:16px; }} .item {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Suivi projet partenaire</h1>
    <div>Etat d'avancement, modules disponibles, prochaines decisions et criteres de demonstration.</div>
    <nav>
      <a href="{self.admin_link("/dashboard")}">Tableau de bord</a>
      <a href="{self.admin_link("/architecture")}">Architecture</a>
      <a href="{self.admin_link("/roadmap")}">Suivi projet</a>
    </nav>
  </header>
  <main>
    <section class="grid">
      <div class="panel span-3"><h2>Statut</h2><span class="tag">Demo pre-prod</span><div class="kpi">V0.1</div></div>
      <div class="panel span-3"><h2>Modules</h2><div class="kpi">7</div><p>API, dashboard, SMS, securite, architecture, fiche compteur, demo.</p></div>
      <div class="panel span-3"><h2>Tests</h2><div class="kpi">7 OK</div><p>Suite automatique et scenario API valides.</p></div>
      <div class="panel span-3"><h2>Priorite</h2><div class="kpi">SMS reel</div><p>Choix fournisseur et credentials.</p></div>

      <div class="panel span-6">
        <h2>Avancement par chantier</h2>
        {self.progress_html("Moteur PROTEC MVP", 100)}
        {self.progress_html("Dashboard partenaire", 90)}
        {self.progress_html("Architecture lisible DAF/DSI", 90)}
        {self.progress_html("Securite admin optionnelle", 75)}
        {self.progress_html("Mise en ligne pilote", 50)}
        {self.progress_html("SMS fournisseur reel", 35)}
      </div>
      <div class="panel span-6">
        <h2>Scenario de demonstration</h2>
        <div class="timeline">
          <div class="item"><div class="date">Etape 1</div><div><strong>Souscription</strong><p>La SEEG envoie une demande de protection compteur via webhook.</p></div></div>
          <div class="item"><div class="date">Etape 2</div><div><strong>Paiement</strong><p>Le paiement active l'abonnement et rend le compteur eligible aux alertes.</p></div></div>
          <div class="item"><div class="date">Etape 3</div><div><strong>Alerte</strong><p>Une baisse de solde declenche un calcul de jours restants et un SMS.</p></div></div>
          <div class="item"><div class="date">Etape 4</div><div><strong>Suivi</strong><p>Le dashboard affiche abonnement, paiement, SMS, anti-doublon et historique.</p></div></div>
        </div>
      </div>

      <div class="panel span-12">
        <h2>Plan de mise en ligne partenaire</h2>
        <table>
          <thead><tr><th>Lot</th><th>Objectif</th><th>Preuve attendue</th><th>Statut</th></tr></thead>
          <tbody>
            <tr><td>Lot 1</td><td>Demo locale stable</td><td>Script demo + dashboard + fiche compteur</td><td>Termine</td></tr>
            <tr><td>Lot 2</td><td>Acces partenaire protege</td><td>Token admin + URL partageable</td><td>En cours</td></tr>
            <tr><td>Lot 3</td><td>SMS reel</td><td>Fournisseur configure, test bout en bout</td><td>A faire</td></tr>
            <tr><td>Lot 4</td><td>Donnees SEEG pilote</td><td>Format webhook ou fichier EDAN valide</td><td>A faire</td></tr>
            <tr><td>Lot 5</td><td>Hebergement pilote</td><td>HTTPS, sauvegarde DB, monitoring</td><td>A faire</td></tr>
          </tbody>
        </table>
      </div>

      <div class="panel span-6">
        <h2>Ce que les partenaires peuvent verifier</h2>
        <p>Le partenaire peut suivre le flux complet : compteur souscrit, paiement confirme, alerte faible, SMS genere, doublon bloque, historique visible.</p>
      </div>
      <div class="panel span-6">
        <h2>Decisions a prendre</h2>
        <p>Choisir le fournisseur SMS, definir le format exact des donnees SEEG, choisir l'hebergement pilote et valider le niveau d'acces partenaire.</p>
      </div>
    </section>
  </main>
</body>
</html>"""

    def architecture_html(self) -> str:
        return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(settings.app_name)} - Architecture</title>
  <style>
    body {{ font-family:"Segoe UI", Arial, sans-serif; margin:0; background:#f4f7f8; color:#142126; }}
    header {{ background:linear-gradient(135deg, #173f49, #0b6b4f); color:white; padding:22px 28px; }}
    main {{ max-width:1180px; margin:0 auto; padding:22px 28px 34px; }}
    h1 {{ margin:0 0 6px; font-size:28px; }}
    h2 {{ margin:24px 0 12px; font-size:19px; }}
    .panel {{ background:white; border:1px solid #d8e1e4; border-radius:8px; padding:18px; margin-bottom:16px; box-shadow:0 8px 20px rgba(20,33,38,.04); }}
    .flow {{ display:grid; grid-template-columns:repeat(5, 1fr); gap:10px; align-items:stretch; }}
    .step {{ border:1px solid #d8e1e4; border-radius:8px; padding:14px; background:#fbfdfd; }}
    .step strong {{ display:block; margin-bottom:8px; color:#0b6b4f; }}
    ol li {{ margin:10px 0; }}
    code {{ background:#eef5f3; padding:2px 5px; border-radius:4px; }}
    a {{ color:#0b6b4f; }}
    svg {{ width:100%; height:auto; background:white; border:1px solid #d8e1e4; border-radius:8px; }}
    @media (max-width:900px) {{ .flow {{ grid-template-columns:1fr; }} main {{ padding:16px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(settings.app_name)} - Architecture fonctionnelle</h1>
    <div>Comprendre ce qui se passe derriere le dashboard.</div>
  </header>
  <main>
    <p><a href="{self.admin_link("/dashboard")}">Retour au tableau de bord</a></p>
    <section class="panel">
      <h2>Vue d'ensemble</h2>
      <div class="flow">
        <div class="step"><strong>Client</strong>Souscrit au service et associe son compteur a un numero mobile.</div>
        <div class="step"><strong>SEEG</strong>Envoie des webhooks HTTP vers SEEG Protect.</div>
        <div class="step"><strong>API</strong>Verifie la signature, valide le JSON et declenche la logique metier.</div>
        <div class="step"><strong>Stockage</strong>Conserve abonnements, paiements, notifications et evenements.</div>
        <div class="step"><strong>SMS</strong>Simule l'envoi dans l'outbox ou appelle un fournisseur SMS reel.</div>
      </div>
    </section>
    <section class="panel">
      <h2>Schema technique</h2>
      {self.architecture_svg()}
    </section>
    <section class="panel">
      <h2>Scenario exemple</h2>
      <ol>
        <li>Un client demande l'activation de SEEG Protect pour son compteur <code>api-meter-...</code>.</li>
        <li>La SEEG appelle <code>POST /webhooks/subscriptions</code>. Le service cree une souscription en attente de paiement.</li>
        <li>Apres paiement, la SEEG appelle <code>POST /webhooks/payments</code>. La souscription passe a <code>active</code>.</li>
        <li>Quand le solde est faible, la SEEG appelle <code>POST /webhooks/low-balance</code> avec le solde restant.</li>
        <li>SEEG Protect calcule les jours restants, verifie l'anti-doublon, puis cree un SMS.</li>
        <li>En mode demo, le SMS est ecrit dans <code>logs/sms_outbox.jsonl</code>. En production, il part vers le fournisseur SMS.</li>
        <li>Le dashboard lit SQLite et affiche les resultats : compteur actif, paiement, SMS, evenements.</li>
      </ol>
    </section>
    <section class="panel">
      <h2>Point important</h2>
      <p>Il n'y a pas d'appel telephonique vocal dans ce MVP. Les "appels" sont des appels HTTP entre systemes. Le client recoit un SMS, pas un appel vocal.</p>
    </section>
  </main>
</body>
</html>"""

    @staticmethod
    def stat_html(label: str, value: int | str) -> str:
        return f'<div class="stat span-3"><div class="label">{escape(label)}</div><div class="value">{escape(str(value))}</div></div>'

    @staticmethod
    def hidden_token_input() -> str:
        if not settings.admin_token:
            return ""
        return f'<input type="hidden" name="token" value="{escape(settings.admin_token)}">'

    @staticmethod
    def bar_chart_html(rows: list[dict[str, Any]], label_key: str) -> str:
        if not rows:
            return '<p class="subtle">Aucune donnee disponible.</p>'
        max_value = max(int(row["total"]) for row in rows) or 1
        parts = []
        for row in rows:
            label = str(row.get(label_key) or "inconnu")
            total = int(row["total"])
            width = max(4, round((total / max_value) * 100))
            parts.append(
                f'<div class="bar-row"><span>{escape(label)}</span>'
                f'<div class="bar-track"><div class="bar-fill" style="width:{width}%"></div></div>'
                f'<strong>{total}</strong></div>'
            )
        return "".join(parts)

    @staticmethod
    def timeline_html(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return '<p class="subtle">Aucun SMS enregistre.</p>'
        max_value = max(int(row["total"]) for row in rows) or 1
        parts = []
        for row in rows:
            total = int(row["total"])
            height = max(6, round((total / max_value) * 130))
            label = str(row["day"])[5:]
            parts.append(
                f'<div class="day"><div class="day-bar" title="{total} SMS" style="height:{height}px"></div>'
                f'<div class="day-label">{escape(label)}</div></div>'
            )
        return f'<div class="timeline">{"".join(parts)}</div>'

    @staticmethod
    def donut_chart_html(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return '<p class="subtle">Aucun statut SMS disponible.</p>'
        total = sum(int(row["total"]) for row in rows) or 1
        first = rows[0]
        first_value = int(first["total"])
        first_percent = round((first_value / total) * 100)
        legend = []
        for row in rows:
            label = str(row.get("status") or "inconnu")
            value = int(row["total"])
            percent = round((value / total) * 100)
            legend.append(
                f'<div class="bar-row"><span>{escape(label)}</span>'
                f'<div class="bar-track"><div class="bar-fill" style="width:{max(4, percent)}%"></div></div>'
                f'<strong>{value}</strong></div>'
            )
        return (
            '<div style="display:grid;grid-template-columns:130px 1fr;gap:16px;align-items:center">'
            f'<div style="width:120px;height:120px;border-radius:50%;background:conic-gradient(#0b6b4f 0 {first_percent}%, #dfe8eb {first_percent}% 100%);display:grid;place-items:center">'
            f'<div style="width:76px;height:76px;border-radius:50%;background:white;display:grid;place-items:center;font-weight:800;color:#0b6b4f">{total}</div>'
            '</div>'
            f'<div>{"".join(legend)}</div>'
            '</div>'
        )

    @staticmethod
    def progress_html(label: str, percent: int) -> str:
        safe_percent = max(0, min(percent, 100))
        return (
            f'<div style="margin:10px 0"><div style="display:flex;justify-content:space-between;gap:12px">'
            f'<strong>{escape(label)}</strong><span>{safe_percent}%</span></div>'
            f'<div class="bar"><div class="fill" style="width:{safe_percent}%"></div></div></div>'
        )

    @staticmethod
    def architecture_svg() -> str:
        return """<svg viewBox="0 0 1120 420" role="img" aria-label="Architecture SEEG Protect">
  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">
      <path d="M0,0 L0,6 L9,3 z" fill="#0b6b4f" />
    </marker>
  </defs>
  <rect x="40" y="60" width="160" height="80" rx="8" fill="#eef5f3" stroke="#0b6b4f"/>
  <text x="120" y="92" text-anchor="middle" font-size="16" font-weight="700" fill="#142126">Client</text>
  <text x="120" y="116" text-anchor="middle" font-size="12" fill="#56666d">numero mobile</text>
  <rect x="270" y="60" width="170" height="80" rx="8" fill="#ffffff" stroke="#0b6b4f"/>
  <text x="355" y="92" text-anchor="middle" font-size="16" font-weight="700" fill="#142126">Systeme SEEG</text>
  <text x="355" y="116" text-anchor="middle" font-size="12" fill="#56666d">webhooks HTTP signes</text>
  <rect x="510" y="60" width="170" height="80" rx="8" fill="#ffffff" stroke="#0b6b4f"/>
  <text x="595" y="88" text-anchor="middle" font-size="16" font-weight="700" fill="#142126">API SEEG Protect</text>
  <text x="595" y="112" text-anchor="middle" font-size="12" fill="#56666d">validation + metier</text>
  <rect x="750" y="60" width="150" height="80" rx="8" fill="#ffffff" stroke="#0b6b4f"/>
  <text x="825" y="92" text-anchor="middle" font-size="16" font-weight="700" fill="#142126">SQLite</text>
  <text x="825" y="116" text-anchor="middle" font-size="12" fill="#56666d">donnees + logs</text>
  <rect x="960" y="60" width="130" height="80" rx="8" fill="#eef5f3" stroke="#0b6b4f"/>
  <text x="1025" y="92" text-anchor="middle" font-size="16" font-weight="700" fill="#142126">Dashboard</text>
  <text x="1025" y="116" text-anchor="middle" font-size="12" fill="#56666d">suivi metier</text>
  <rect x="510" y="245" width="170" height="80" rx="8" fill="#fff8eb" stroke="#c47a00"/>
  <text x="595" y="278" text-anchor="middle" font-size="16" font-weight="700" fill="#142126">SMS Gateway</text>
  <text x="595" y="302" text-anchor="middle" font-size="12" fill="#56666d">stub ou fournisseur</text>
  <rect x="750" y="245" width="150" height="80" rx="8" fill="#fff8eb" stroke="#c47a00"/>
  <text x="825" y="278" text-anchor="middle" font-size="16" font-weight="700" fill="#142126">Outbox SMS</text>
  <text x="825" y="302" text-anchor="middle" font-size="12" fill="#56666d">sms_outbox.jsonl</text>
  <line x1="200" y1="100" x2="270" y2="100" stroke="#0b6b4f" stroke-width="3" marker-end="url(#arrow)"/>
  <line x1="440" y1="100" x2="510" y2="100" stroke="#0b6b4f" stroke-width="3" marker-end="url(#arrow)"/>
  <line x1="680" y1="100" x2="750" y2="100" stroke="#0b6b4f" stroke-width="3" marker-end="url(#arrow)"/>
  <line x1="900" y1="100" x2="960" y2="100" stroke="#0b6b4f" stroke-width="3" marker-end="url(#arrow)"/>
  <line x1="595" y1="140" x2="595" y2="245" stroke="#c47a00" stroke-width="3" marker-end="url(#arrow)"/>
  <line x1="680" y1="285" x2="750" y2="285" stroke="#c47a00" stroke-width="3" marker-end="url(#arrow)"/>
  <text x="355" y="176" text-anchor="middle" font-size="13" fill="#56666d">subscription / payment / low-balance</text>
  <text x="220" y="46" text-anchor="middle" font-size="13" fill="#56666d">Le client agit dans le parcours SEEG</text>
  <text x="708" y="214" text-anchor="middle" font-size="13" fill="#56666d">Notification apres calcul des jours restants</text>
</svg>"""

    @staticmethod
    def table_html(rows: list[dict[str, Any]], columns: list[str]) -> str:
        if not rows:
            return "<p>Aucune donnee.</p>"
        head = "".join(f"<th>{escape(column)}</th>" for column in columns)
        body_rows = []
        for row in rows:
            cells = "".join(f"<td>{escape(str(row.get(column) or ''))}</td>" for column in columns)
            body_rows.append(f"<tr>{cells}</tr>")
        return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"

    def log_message(self, format: str, *args: Any) -> None:
        return


def run() -> None:
    server = ThreadingHTTPServer((settings.host, settings.port), ApiHandler)
    print(f"SEEG Protect API running on http://{settings.host}:{settings.port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
