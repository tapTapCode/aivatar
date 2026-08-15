from __future__ import annotations

import asyncio
from html import escape
from urllib.parse import quote

import resend


class AuthMailer:
    def __init__(self, *, api_key: str | None, from_email: str, base_url: str) -> None:
        self.api_key = api_key
        self.from_email = from_email
        self.base_url = base_url.rstrip("/")

    def action_url(self, purpose: str, token: str) -> str:
        view = "verify" if purpose == "verify_email" else "reset"
        return f"{self.base_url}/?view={view}&token={quote(token)}"

    async def send_verification(self, email: str, display_name: str, token: str) -> bool:
        return await self._send(
            email=email,
            subject="Verify your Aivatar email",
            heading="Verify your email",
            copy="Confirm your email address to activate your Aivatar workspace.",
            action_label="Verify email",
            action_url=self.action_url("verify_email", token),
            display_name=display_name,
        )

    async def send_password_reset(self, email: str, display_name: str, token: str) -> bool:
        return await self._send(
            email=email,
            subject="Reset your Aivatar password",
            heading="Reset your password",
            copy="Use this secure link to choose a new password. It expires shortly.",
            action_label="Reset password",
            action_url=self.action_url("reset_password", token),
            display_name=display_name,
        )

    async def _send(
        self,
        *,
        email: str,
        subject: str,
        heading: str,
        copy: str,
        action_label: str,
        action_url: str,
        display_name: str,
    ) -> bool:
        if not self.api_key:
            return False
        safe_name = escape(display_name)
        safe_url = escape(action_url, quote=True)
        html = f"""
        <div style="font-family:Inter,Arial,sans-serif;background:#050913;color:#f5f8ff;
                    padding:36px">
          <div style="max-width:560px;margin:auto;background:#0b1222;border:1px solid #24345b;
                      border-radius:18px;padding:36px">
            <strong style="font-size:24px">Aivatar</strong>
            <h1 style="font-size:24px;margin-top:32px">{escape(heading)}</h1>
            <p>Hello {safe_name},</p>
            <p style="color:#a8b5d4;line-height:1.6">{escape(copy)}</p>
            <a href="{safe_url}" style="display:inline-block;margin-top:18px;padding:13px 20px;
               border-radius:10px;background:#2f80ed;color:white;text-decoration:none">
              {escape(action_label)}
            </a>
            <p style="margin-top:28px;color:#7786a8;font-size:12px">
              If you did not request this, you can safely ignore this email.
            </p>
          </div>
        </div>
        """

        def deliver() -> None:
            resend.api_key = self.api_key or ""
            resend.Emails.send(
                {
                    "from": self.from_email,
                    "to": [email],
                    "subject": subject,
                    "html": html,
                }
            )

        try:
            await asyncio.to_thread(deliver)
        except Exception:
            return False
        return True
