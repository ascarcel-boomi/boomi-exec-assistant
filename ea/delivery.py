"""Output routing — stdout and/or Gmail."""


class Deliverer:
    def __init__(self, gmail_client, cfg):
        self.gmail = gmail_client
        self.cfg = cfg

    def deliver(
        self,
        subject: str,
        body: str,
        task_name: str = "",
        dry_run: bool = False,
    ) -> None:
        if self.cfg.deliver_to_stdout:
            width = 70
            print(f"\n{'=' * width}")
            print(f"  {subject}")
            print(f"{'=' * width}")
            print(body)
            print()

        if self.cfg.deliver_to_email and not dry_run:
            try:
                self.gmail.send_message(
                    to=self.cfg.email,
                    subject=f"[EA] {subject}",
                    body=body,
                )
            except Exception as e:
                print(f"[EA] Warning: could not send email — {e}")
