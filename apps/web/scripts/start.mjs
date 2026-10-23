import {cpSync, existsSync} from "node:fs";
import {resolve} from "node:path";
import {pathToFileURL} from "node:url";

const portIndex = process.argv.indexOf("--port");
if (portIndex !== -1) process.env.PORT = process.argv[portIndex + 1];
process.env.HOSTNAME ||= "127.0.0.1";
const server = resolve(".next/standalone/server.js");
if (!existsSync(server)) throw new Error("Run npm run build before starting the production server.");
cpSync(".next/static", ".next/standalone/.next/static", {recursive:true});
if (existsSync("public")) cpSync("public", ".next/standalone/public", {recursive:true});
await import(pathToFileURL(server).href);
