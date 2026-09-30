// Runs the mock controller (18450) and `next dev` (3110) pointed at it.
import { spawn } from "node:child_process";
const MOCK = process.env.MOCK_PORT || "18450";
const UI = process.env.PORT || "3110";
const env = { ...process.env, MOCK_PORT: MOCK, LIVE_UI_BASE_URL: `http://127.0.0.1:${UI}`, NEXT_PUBLIC_CONTROLLER_URL: `http://127.0.0.1:${MOCK}` };
const kids = [
  spawn(process.execPath, ["scripts/mock-controller.mjs"], { stdio: "inherit", env }),
  spawn(process.execPath, ["node_modules/next/dist/bin/next", "dev", "-p", UI], { stdio: "inherit", env }),
];
const stop = () => kids.forEach((k) => k.kill());
kids.forEach((k) => k.on("exit", stop));
for (const s of ["SIGINT", "SIGTERM"]) process.on(s, stop);
