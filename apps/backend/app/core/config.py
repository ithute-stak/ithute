from functools import lru_cache
from ipaddress import ip_address

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Mailbox DNS"
    environment: str = "development"
    platform_mode: str = "bootstrap"
    bootstrap_public_ip: str | None = None
    caddy_admin_url: str = "http://caddy:2019"
    caddy_runtime_file: str = "/platform-runtime/Caddyfile"

    secret_key: str
    dkim_encryption_key: str | None = None
    dkim_encryption_key_id: str = "v1"
    billing_webhook_secret: str | None = None
    billing_grace_days: int = 7
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    invitation_expire_hours: int = 72
    email_verification_expire_hours: int = 24

    database_url: str
    redis_url: str = "redis://redis:6379/0"
    rspamd_redis_url: str = "redis://rspamd-redis:6379/0"
    backup_status_dir: str = "/backup-status/status"
    backup_max_age_seconds: int = 93600
    prometheus_url: str = "http://prometheus:9090"
    prometheus_timeout_seconds: float = 5.0
    operations_slo_target: float = 0.999
    frontend_url: str = "http://localhost:3006"

    bootstrap_admin_email: str = "admin@example.com"
    bootstrap_admin_password: str = "ChangeMe123!"
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    access_cookie_name: str = "mdns_access"
    refresh_cookie_name: str = "mdns_refresh"

    signup_rate_window_seconds: int = 3600
    signup_rate_max_attempts: int = 20

    system_email_from: str | None = None
    system_smtp_host: str | None = None
    system_smtp_port: int = 587
    system_smtp_username: str | None = None
    system_smtp_password: str | None = None
    system_smtp_ssl: bool = False
    system_smtp_starttls: bool = True

    nameserver_1: str = "ns1.mailbox-dns.example"
    nameserver_2: str = "ns2.mailbox-dns.example"

    mail_hostname: str = "mail.phase8.test"
    mail_public_ip: str | None = None
    mail_tls_mode: str = "selfsigned"
    mail_data_path: str = "/srv/vmail"
    mail_ops_url: str = "http://postfix:9080"
    mail_ops_token: str = "development-mail-ops-token-change-me"
    mail_ops_timeout_seconds: float = 5.0

    recovery_ops_url: str = "http://backup-recovery:9081"
    recovery_ops_token: str = "development-recovery-ops-token-change-me"
    recovery_ops_timeout_seconds: float = 120.0

    webmail_session_cookie_name: str = "mdns_webmail"
    webmail_session_ttl_seconds: int = 28800
    webmail_imap_host: str = "dovecot"
    webmail_imap_port: int = 143
    webmail_smtp_host: str = "postfix"
    webmail_smtp_port: int = 587
    webmail_transport_timeout_seconds: int = 15
    webmail_login_max_attempts: int = 8
    webmail_login_window_seconds: int = 900
    webmail_login_lock_seconds: int = 900

    transactional_smtp_host: str = "postfix"
    transactional_smtp_port: int = 587
    transactional_smtp_verify_tls: bool = False
    transactional_default_daily_limit: int = 1000
    transactional_tenant_daily_limit: int = 10000
    transactional_max_recipients: int = 100

    groupware_public_url: str = "http://localhost:5232"
    groupware_auth_file: str = "/groupware-auth/users"

    mail_node_token: str | None = None
    mail_node_stale_seconds: int = 180

    domain_verification_min_interval_seconds: int = 10
    domain_verification_max_attempts_per_hour: int = 20

    powerdns_api_url: str = "http://powerdns:8081/api/v1"
    powerdns_api_key: str = "development-powerdns-api-key-change-me"
    powerdns_server_id: str = "localhost"
    powerdns_api_timeout_seconds: float = 5.0
    powerdns_default_ttl: int = 3600

    external_provider_timeout_seconds: float = 20.0

    dpo_api_url: str = "https://secure.3gdirectpay.com/API/v6/"
    dpo_checkout_url: str = "https://secure.3gdirectpay.com/payv2.php?ID={token}"
    dpo_company_token: str | None = None
    dpo_service_type: str | None = None
    dpo_redirect_url: str = "http://localhost:3006/billing"
    dpo_back_url: str = "http://localhost:8006/api/v1/payments/dpo/callback"
    dpo_payment_time_limit_hours: int = 48

    opensrs_api_url: str = "https://rr-n1-tor.opensrs.net:55443/"
    opensrs_username: str | None = None
    opensrs_api_key: str | None = None

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    @model_validator(mode="after")
    def validate_security(self):
        if len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        if self.platform_mode not in {"bootstrap", "domain"}:
            raise ValueError("PLATFORM_MODE must be bootstrap or domain")
        if not self.caddy_admin_url.startswith(("http://", "https://")):
            raise ValueError("CADDY_ADMIN_URL must be an HTTP(S) URL")
        if not self.caddy_runtime_file.startswith("/"):
            raise ValueError("CADDY_RUNTIME_FILE must be an absolute path")
        if self.dkim_encryption_key:
            self.dkim_encryption_key = self.dkim_encryption_key.strip()
            if len(self.dkim_encryption_key) < 32:
                raise ValueError("DKIM_ENCRYPTION_KEY must be at least 32 characters")
        else:
            self.dkim_encryption_key = None
        if self.billing_webhook_secret:
            self.billing_webhook_secret = self.billing_webhook_secret.strip()
            if len(self.billing_webhook_secret) < 32:
                raise ValueError("BILLING_WEBHOOK_SECRET must be at least 32 characters when configured")
        else:
            self.billing_webhook_secret = None
        if not 1 <= self.billing_grace_days <= 90:
            raise ValueError("BILLING_GRACE_DAYS must be between 1 and 90")
        if not 1 <= self.email_verification_expire_hours <= 168:
            raise ValueError("EMAIL_VERIFICATION_EXPIRE_HOURS must be between 1 and 168")
        if not 60 <= self.signup_rate_window_seconds <= 86400 or not 1 <= self.signup_rate_max_attempts <= 1000:
            raise ValueError("Signup rate limit configuration is invalid")
        if not self.dkim_encryption_key_id.strip() or len(self.dkim_encryption_key_id) > 32:
            raise ValueError("DKIM_ENCRYPTION_KEY_ID must be a non-empty value up to 32 characters")
        if not self.rspamd_redis_url.startswith(("redis://", "rediss://")):
            raise ValueError("RSPAMD_REDIS_URL must be a Redis URL")
        if not self.backup_status_dir.startswith("/"):
            raise ValueError("BACKUP_STATUS_DIR must be an absolute path")
        if not 3600 <= self.backup_max_age_seconds <= 604800:
            raise ValueError("BACKUP_MAX_AGE_SECONDS must be between 3600 and 604800")
        if not self.prometheus_url.startswith(("http://", "https://")):
            raise ValueError("PROMETHEUS_URL must be an HTTP(S) URL")
        if not 0.5 <= self.prometheus_timeout_seconds <= 30:
            raise ValueError("PROMETHEUS_TIMEOUT_SECONDS must be between 0.5 and 30")
        if not 0.9 <= self.operations_slo_target < 1.0:
            raise ValueError("OPERATIONS_SLO_TARGET must be between 0.9 and 1.0")
        if len(self.bootstrap_admin_password) < 12:
            raise ValueError("BOOTSTRAP_ADMIN_PASSWORD must be at least 12 characters")
        if self.cookie_samesite not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE must be lax, strict, or none")
        if self.mail_tls_mode not in {"selfsigned", "acme", "external"}:
            raise ValueError("MAIL_TLS_MODE must be selfsigned, acme, or external")
        if not self.mail_data_path.startswith("/"):
            raise ValueError("MAIL_DATA_PATH must be absolute")
        if not self.recovery_ops_url.startswith(("http://", "https://")) or len(self.recovery_ops_token) < 24:
            raise ValueError("Recovery service configuration is invalid")
        if not 2 <= self.recovery_ops_timeout_seconds <= 600:
            raise ValueError("RECOVERY_OPS_TIMEOUT_SECONDS must be between 2 and 600")
        if not 900 <= self.webmail_session_ttl_seconds <= 86400:
            raise ValueError("WEBMAIL_SESSION_TTL_SECONDS must be between 900 and 86400")
        if not 3 <= self.webmail_login_max_attempts <= 100:
            raise ValueError("WEBMAIL_LOGIN_MAX_ATTEMPTS must be between 3 and 100")
        if not 60 <= self.webmail_login_window_seconds <= 86400:
            raise ValueError("WEBMAIL_LOGIN_WINDOW_SECONDS must be between 60 and 86400")
        if not 60 <= self.webmail_login_lock_seconds <= 86400:
            raise ValueError("WEBMAIL_LOGIN_LOCK_SECONDS must be between 60 and 86400")
        if not 1 <= self.webmail_imap_port <= 65535 or not 1 <= self.webmail_smtp_port <= 65535:
            raise ValueError("Webmail IMAP/SMTP ports must be valid TCP ports")
        if not self.webmail_imap_host.strip() or not self.webmail_smtp_host.strip():
            raise ValueError("Webmail IMAP/SMTP hosts must be non-empty")
        if not 2 <= self.webmail_transport_timeout_seconds <= 60:
            raise ValueError("WEBMAIL_TRANSPORT_TIMEOUT_SECONDS must be between 2 and 60")
        if not 1 <= self.transactional_smtp_port <= 65535:
            raise ValueError("TRANSACTIONAL_SMTP_PORT must be a valid TCP port")
        if not 1 <= self.transactional_default_daily_limit <= 1_000_000 or not 1 <= self.transactional_tenant_daily_limit <= 10_000_000:
            raise ValueError("Transactional mail limits are invalid")
        if not 1 <= self.transactional_max_recipients <= 1000:
            raise ValueError("TRANSACTIONAL_MAX_RECIPIENTS must be between 1 and 1000")
        if not self.groupware_auth_file.startswith("/"):
            raise ValueError("GROUPWARE_AUTH_FILE must be absolute")
        if not 30 <= self.mail_node_stale_seconds <= 3600:
            raise ValueError("MAIL_NODE_STALE_SECONDS must be between 30 and 3600")
        if not self.nameserver_1.strip() or not self.nameserver_2.strip() or self.nameserver_1.lower() == self.nameserver_2.lower():
            raise ValueError("NAMESERVER_1 and NAMESERVER_2 must be distinct non-empty hostnames")
        if not self.mail_hostname.strip() or "." not in self.mail_hostname.strip().rstrip("."):
            raise ValueError("MAIL_HOSTNAME must be a fully-qualified hostname")
        if self.bootstrap_public_ip:
            try:
                bootstrap_ip = ip_address(self.bootstrap_public_ip.strip())
            except ValueError as exc:
                raise ValueError("BOOTSTRAP_PUBLIC_IP must be a valid IP address") from exc
            if self.environment.lower() == "production" and not bootstrap_ip.is_global:
                raise ValueError("Production BOOTSTRAP_PUBLIC_IP must be globally routable")
        if self.mail_public_ip:
            try:
                parsed = ip_address(self.mail_public_ip.strip())
            except ValueError as exc:
                raise ValueError("MAIL_PUBLIC_IP must be a valid IP address") from exc
            if parsed.is_loopback or parsed.is_unspecified or parsed.is_multicast:
                raise ValueError("MAIL_PUBLIC_IP must identify a usable mail-server address")
        if not self.mail_ops_url.startswith(("http://", "https://")):
            raise ValueError("MAIL_OPS_URL must be an HTTP(S) URL")
        if len(self.mail_ops_token) < 24:
            raise ValueError("MAIL_OPS_TOKEN must be at least 24 characters")
        if not 0.5 <= self.mail_ops_timeout_seconds <= 30:
            raise ValueError("MAIL_OPS_TIMEOUT_SECONDS must be between 0.5 and 30")
        if not 5 <= self.domain_verification_min_interval_seconds <= 3600:
            raise ValueError("DOMAIN_VERIFICATION_MIN_INTERVAL_SECONDS must be between 5 and 3600")
        if not 1 <= self.domain_verification_max_attempts_per_hour <= 100:
            raise ValueError("DOMAIN_VERIFICATION_MAX_ATTEMPTS_PER_HOUR must be between 1 and 100")
        if not self.powerdns_api_url.startswith(("http://", "https://")):
            raise ValueError("POWERDNS_API_URL must be an HTTP(S) URL")
        if not 0.5 <= self.powerdns_api_timeout_seconds <= 30:
            raise ValueError("POWERDNS_API_TIMEOUT_SECONDS must be between 0.5 and 30")
        if not 60 <= self.powerdns_default_ttl <= 86400:
            raise ValueError("POWERDNS_DEFAULT_TTL must be between 60 and 86400")
        if not 2 <= self.external_provider_timeout_seconds <= 120:
            raise ValueError("EXTERNAL_PROVIDER_TIMEOUT_SECONDS must be between 2 and 120")
        if self.dpo_company_token and not self.dpo_service_type:
            raise ValueError("DPO_SERVICE_TYPE is required when DPO_COMPANY_TOKEN is configured")
        if self.opensrs_username and not self.opensrs_api_key:
            raise ValueError("OPENSRS_API_KEY is required when OPENSRS_USERNAME is configured")
        if not 1 <= self.dpo_payment_time_limit_hours <= 168:
            raise ValueError("DPO_PAYMENT_TIME_LIMIT_HOURS must be between 1 and 168")

        if self.environment.lower() == "production":
            insecure_markers = ("change-this", "change-me", "changeme", "replace-with", "example-secret", "development-only")
            if not self.dkim_encryption_key:
                raise ValueError("Production requires a dedicated DKIM_ENCRYPTION_KEY")
            if not self.billing_webhook_secret:
                raise ValueError("Production requires BILLING_WEBHOOK_SECRET")
            secret_values = (
                self.secret_key.lower(),
                self.dkim_encryption_key.lower(),
                self.billing_webhook_secret.lower(),
                self.bootstrap_admin_password.lower(),
                self.powerdns_api_key.lower(),
                self.mail_ops_token.lower(),
                self.recovery_ops_token.lower(),
            )
            if any(marker in value for marker in insecure_markers for value in secret_values):
                raise ValueError("Production refuses placeholder application, DKIM, billing, bootstrap, PowerDNS, mail-operations, or recovery secrets")
            if self.dkim_encryption_key == self.secret_key:
                raise ValueError("Production DKIM_ENCRYPTION_KEY must be distinct from SECRET_KEY")
            if self.billing_webhook_secret in {self.secret_key, self.dkim_encryption_key}:
                raise ValueError("Production BILLING_WEBHOOK_SECRET must be distinct from application and DKIM secrets")
            if self.rspamd_redis_url == self.redis_url:
                raise ValueError("Production RSPAMD_REDIS_URL must be isolated from application REDIS_URL")
            if len(self.powerdns_api_key) < 24:
                raise ValueError("Production POWERDNS_API_KEY must be at least 24 characters")
            if not self.bootstrap_public_ip:
                raise ValueError("Production requires BOOTSTRAP_PUBLIC_IP")
            if not self.mail_public_ip:
                raise ValueError("Production requires MAIL_PUBLIC_IP for PTR/HELO deliverability validation")
            parsed = ip_address(self.mail_public_ip.strip())
            if not parsed.is_global:
                raise ValueError("Production MAIL_PUBLIC_IP must be globally routable")
            if self.mail_ops_url.startswith("https://") is False and not any(host in self.mail_ops_url for host in ("postfix", "127.0.0.1", "localhost")):
                raise ValueError("Production MAIL_OPS_URL must use HTTPS unless it targets the private Postfix service")
            if not self.mail_node_token or len(self.mail_node_token) < 24:
                raise ValueError("Production requires a strong MAIL_NODE_TOKEN")

            if self.platform_mode == "domain":
                if not self.cookie_secure:
                    raise ValueError("Domain production mode requires COOKIE_SECURE=true")
                if self.nameserver_1.endswith(".example") or self.nameserver_2.endswith(".example"):
                    raise ValueError("Domain production mode requires real authoritative nameserver hostnames")
                if self.mail_hostname.endswith((".test", ".example", ".localhost")):
                    raise ValueError("Domain production mode requires a real public MAIL_HOSTNAME")
                if self.mail_tls_mode == "selfsigned":
                    raise ValueError("Domain production mode requires MAIL_TLS_MODE=acme or external")
                if not self.system_email_from or not self.system_smtp_host:
                    raise ValueError("Domain production mode requires SYSTEM_EMAIL_FROM and SYSTEM_SMTP_HOST for customer verification")
                if not (self.system_smtp_ssl or self.system_smtp_starttls):
                    raise ValueError("Domain production mode system SMTP must use TLS")
                if not self.groupware_public_url.startswith("https://"):
                    raise ValueError("Domain production mode GROUPWARE_PUBLIC_URL must use HTTPS")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
