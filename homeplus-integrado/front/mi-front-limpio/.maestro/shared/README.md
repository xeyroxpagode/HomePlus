# Shared Maestro flows

`login.yaml` receives `QA_EMAIL` and `QA_PASSWORD` from the process environment.
`ensure-authenticated.yaml` launches the app, waits for the resolved Auth gate,
and either reuses the device session or logs in as `QA_A`. No credential, token,
or Auth bypass is committed to a flow.
