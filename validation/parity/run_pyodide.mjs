// Run case.py in Pyodide under Node. Usage:
//   node run_pyodide.mjs <wheel> <fixtures_dir> <out.json> [archive_to_verify.zip]
import { loadPyodide } from "pyodide";
import fs from "node:fs";
import path from "node:path";

const [wheel, fixtures, out, other] = process.argv.slice(2);
const py = await loadPyodide();
await py.loadPackage(["numpy", "scipy", "networkx", "pydantic", "pyyaml", "httpx", "micropip"]);
const put = (src, dst) => { py.FS.mkdirTree(path.posix.dirname(dst)); py.FS.writeFile(dst, fs.readFileSync(src)); };
const whl = "/tmp/" + path.basename(wheel);
put(wheel, whl);
for (const f of fs.readdirSync(fixtures)) put(path.join(fixtures, f), "/fixtures/" + f);
if (other) put(other, "/tmp/other.zip");
await py.runPythonAsync(`import micropip\nawait micropip.install("emfs:${whl}", deps=False)`);
py.runPython(`import os\nos.environ.update(FIXTURES="/fixtures", OUT="/tmp/fp.json", WORKDIR="/tmp/work"${other ? ', VERIFY_ARCHIVE="/tmp/other.zip"' : ""})`);
py.runPython(fs.readFileSync(new URL("./case.py", import.meta.url), "utf8"));
fs.writeFileSync(out, py.FS.readFile("/tmp/fp.json"));
fs.writeFileSync(out.replace(/\.json$/, ".zip"), py.FS.readFile("/tmp/fp.zip"));
console.log("pyodide", py.runPython("import sys; sys.version.split()[0]"), "->", out);
