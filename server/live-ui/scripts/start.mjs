// `next start` honouring PORT, default 3200.
import { spawn } from "node:child_process";
const port = process.env.PORT || "3200";
const child = spawn(process.execPath, ["node_modules/next/dist/bin/next", "start", "-p", port], { stdio: "inherit", env: process.env });
child.on("exit", (c) => process.exit(c ?? 0));
for (const s of ["SIGINT", "SIGTERM"]) process.on(s, () => child.kill(s));
