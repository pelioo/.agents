"use strict";
/**
 * Browser Launcher - Manages Chrome browser lifecycle
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.CdpPortInUseError = void 0;
exports.isCdpEndpointReachable = isCdpEndpointReachable;
exports.adoptBrowser = adoptBrowser;
exports.probeCdpEndpoint = probeCdpEndpoint;
exports.closeUnattachableCdpBrowser = closeUnattachableCdpBrowser;
exports.getChromePath = getChromePath;
exports.launchBrowser = launchBrowser;
exports.closeBrowser = closeBrowser;
exports.isBrowserRunning = isBrowserRunning;
const child_process_1 = require("child_process");
const fs_1 = require("fs");
const crypto_1 = require("crypto");
const path_1 = require("path");
const os_1 = require("os");
const playwright_core_1 = require("playwright-core");
/**
 * Thrown when the CDP port is already owned by another browser instance.
 * Callers should adopt the existing instance instead of spawning a new one.
 */
class CdpPortInUseError extends Error {
    constructor(message) {
        super(message);
        this.name = 'CdpPortInUseError';
    }
}
exports.CdpPortInUseError = CdpPortInUseError;
/**
 * Probe whether a CDP HTTP endpoint answers on the given port.
 */
async function isCdpEndpointReachable(port, timeoutMs = 1500) {
    try {
        const response = await fetch(`http://127.0.0.1:${port}/json/version`, {
            signal: AbortSignal.timeout(timeoutMs)
        });
        return response.ok;
    }
    catch {
        return false;
    }
}
/**
 * Wrap an already-running CDP browser (e.g. a Chrome that outlived a bridge
 * server restart) as a managed instance without spawning a duplicate.
 */
function adoptBrowser(cdpPort, pid = null) {
    return {
        process: null,
        pid,
        cdpPort,
        startTime: Date.now(),
        adopted: true
    };
}
/**
 * Deep-probe an existing CDP endpoint. /json/version reachability is not
 * enough to adopt a browser: a wedged Chrome can answer HTTP while rejecting
 * every automation client, which would poison all subsequent connects.
 */
async function probeCdpEndpoint(cdpPort) {
    let browser;
    try {
        browser = await playwright_core_1.chromium.connectOverCDP(`http://127.0.0.1:${cdpPort}`, { timeout: 5000 });
    }
    catch {
        return { attachable: false, browserPid: null };
    }
    try {
        const session = await browser.newBrowserCDPSession();
        const info = await session.send('SystemInfo.getProcessInfo');
        const browserProcess = info.processInfo.find(item => item.type === 'browser');
        return {
            attachable: true,
            browserPid: typeof browserProcess?.id === 'number' ? browserProcess.id : null
        };
    }
    catch {
        // Attached but could not read SystemInfo — still adoptable.
        return { attachable: true, browserPid: null };
    }
    finally {
        try {
            await browser.close();
        }
        catch {
            // Disconnect failures are irrelevant here.
        }
    }
}
/**
 * Best-effort shutdown of a CDP browser that answers HTTP but rejects
 * Playwright attachment. Uses a raw WebSocket so the shutdown does not depend
 * on the attach handshake that already failed. Returns true when the endpoint
 * is confirmed gone.
 */
async function closeUnattachableCdpBrowser(cdpPort) {
    if (typeof WebSocket === 'undefined') {
        console.warn('[Browser] Global WebSocket unavailable; cannot close unattachable browser via CDP');
        return false;
    }
    let wsUrl;
    try {
        const response = await fetch(`http://127.0.0.1:${cdpPort}/json/version`, {
            signal: AbortSignal.timeout(2000)
        });
        const data = await response.json();
        wsUrl = data.webSocketDebuggerUrl;
    }
    catch {
        // Endpoint died in the meantime — treat as closed below.
    }
    if (wsUrl) {
        await new Promise(resolve => {
            const socket = new WebSocket(wsUrl);
            const timer = setTimeout(() => {
                try {
                    socket.close();
                }
                catch {
                    // Ignore teardown failures on timeout.
                }
                resolve();
            }, 4000);
            const settle = () => {
                clearTimeout(timer);
                resolve();
            };
            socket.onopen = () => socket.send(JSON.stringify({ id: 1, method: 'Browser.close' }));
            // The browser dropping the socket after Browser.close is the success signal.
            socket.onclose = settle;
            socket.onerror = settle;
        });
    }
    const deadline = Date.now() + 5000;
    while (Date.now() < deadline) {
        if (!(await isCdpEndpointReachable(cdpPort, 800))) {
            return true;
        }
        await new Promise(resolve => setTimeout(resolve, 250));
    }
    return false;
}
/**
 * Detect Chromium-based browser executable path across platforms
 */
function getChromePath() {
    const platform = process.platform;
    const paths = [];
    if (platform === 'darwin') {
        // macOS
        paths.push('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Chromium.app/Contents/MacOS/Chromium', '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge', (0, path_1.join)(process.env.HOME || '', 'Applications/Google Chrome.app/Contents/MacOS/Google Chrome'));
    }
    else if (platform === 'win32') {
        // Windows
        const programFiles = process.env['ProgramFiles'] || 'C:\\Program Files';
        const programFilesX86 = process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)';
        paths.push((0, path_1.join)(programFiles, 'Google\\Chrome\\Application\\chrome.exe'), (0, path_1.join)(programFilesX86, 'Google\\Chrome\\Application\\chrome.exe'), (0, path_1.join)(process.env.LOCALAPPDATA || '', 'Google\\Chrome\\Application\\chrome.exe'), (0, path_1.join)(programFiles, 'Microsoft\\Edge\\Application\\msedge.exe'), (0, path_1.join)(programFilesX86, 'Microsoft\\Edge\\Application\\msedge.exe'), (0, path_1.join)(process.env.LOCALAPPDATA || '', 'Microsoft\\Edge\\Application\\msedge.exe'));
    }
    else {
        // Linux
        paths.push('/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/microsoft-edge', '/usr/bin/microsoft-edge-stable', '/snap/bin/chromium');
    }
    for (const path of paths) {
        if ((0, fs_1.existsSync)(path)) {
            return path;
        }
    }
    throw new Error('No Chromium-based browser found (Chrome/Edge/Chromium). Please install one and retry.');
}
function isDirectoryWritable(path) {
    if (!(0, fs_1.existsSync)(path)) {
        return false;
    }
    try {
        (0, fs_1.accessSync)(path, fs_1.constants.W_OK);
        return true;
    }
    catch {
        return false;
    }
}
function resolveRuntimeChromeFlags(configFlags = []) {
    const runtimeFlags = [...configFlags];
    if (process.platform === 'linux') {
        if (!isDirectoryWritable('/dev/shm')) {
            console.warn('[Browser] /dev/shm is unavailable, enabling --disable-dev-shm-usage');
            runtimeFlags.push('--disable-dev-shm-usage');
        }
        if (!isDirectoryWritable('/dev/mqueue')) {
            console.warn('[Browser] /dev/mqueue is unavailable in this environment');
        }
        if (typeof process.getuid === 'function' && process.getuid() === 0) {
            console.warn('[Browser] Running as root, enabling --no-sandbox');
            runtimeFlags.push('--no-sandbox');
        }
    }
    return Array.from(new Set(runtimeFlags));
}
function resolveHeadlessMode(configHeadless) {
    if (configHeadless) {
        return true;
    }
    if (process.platform !== 'linux') {
        return false;
    }
    const hasDisplay = Boolean(process.env.DISPLAY || process.env.WAYLAND_DISPLAY || process.env.MIR_SOCKET);
    if (hasDisplay) {
        return false;
    }
    console.warn('[Browser] No Linux display detected, forcing headless mode');
    return true;
}
/**
 * Confirm the CDP endpoint we just probed belongs to the Chrome we spawned.
 * waitForCDP only checks that SOMETHING answers on the port; if our spawn lost
 * a bind race, the answer comes from the winner and our Chrome would linger as
 * an unmanaged headed window. A pid mismatch means exactly that.
 */
async function verifySpawnOwnsCdpPort(cdpPort, browserProcess) {
    const probe = await probeCdpEndpoint(cdpPort);
    const ownerPid = probe.browserPid;
    if (ownerPid === null) {
        // Could not determine the owner (endpoint died mid-check or SystemInfo is
        // unavailable). The pre-spawn probe already rejected occupied ports, so
        // fail open rather than killing a legitimately spawned browser.
        console.warn(`[Browser] Could not verify CDP port ${cdpPort} owner; assuming this spawn owns it`);
        return;
    }
    if (ownerPid === browserProcess.pid) {
        return;
    }
    throw new CdpPortInUseError(`CDP port ${cdpPort} is served by another browser process ` +
        `(owner pid=${ownerPid}, spawned pid=${browserProcess.pid ?? 'unknown'})`);
}
/**
 * SIGTERM a spawned Chrome and escalate to SIGKILL if it does not exit in time.
 */
async function terminateSpawnedProcess(browserProcess) {
    if (browserProcess.exitCode !== null || browserProcess.signalCode !== null) {
        return;
    }
    browserProcess.kill('SIGTERM');
    await new Promise(resolve => {
        const timeout = setTimeout(() => {
            if (browserProcess.exitCode === null && browserProcess.signalCode === null) {
                console.log(`[Browser] Force killing browser (PID: ${browserProcess.pid ?? 'unknown'})`);
                browserProcess.kill('SIGKILL');
            }
            resolve();
        }, 5000);
        browserProcess.once('exit', () => {
            clearTimeout(timeout);
            resolve();
        });
    });
}
/**
 * Wait for CDP port to become available
 */
async function waitForCDP(port, browserProcess, timeoutMs = 10000) {
    const startTime = Date.now();
    let attempts = 0;
    while (Date.now() - startTime < timeoutMs) {
        if (browserProcess.exitCode !== null || browserProcess.signalCode !== null) {
            const exitCode = browserProcess.exitCode ?? 'null';
            const signal = browserProcess.signalCode ?? 'none';
            throw new Error(`Chrome process exited before CDP was ready (exitCode=${exitCode}, signal=${signal})`);
        }
        attempts++;
        try {
            const response = await fetch(`http://127.0.0.1:${port}/json/version`, {
                signal: AbortSignal.timeout(2000)
            });
            if (response.ok) {
                console.log(`[Browser] CDP ready after ${attempts} attempts (${Date.now() - startTime}ms)`);
                return;
            }
            console.log(`[Browser] CDP attempt ${attempts}: response not OK (status ${response.status})`);
        }
        catch {
            // Port not ready yet, continue waiting
            if (attempts % 5 === 0) {
                console.log(`[Browser] CDP attempt ${attempts}: still waiting... (${Date.now() - startTime}ms elapsed)`);
            }
        }
        await new Promise(resolve => setTimeout(resolve, 500));
    }
    throw new Error(`CDP port ${port} not ready after ${timeoutMs}ms (${attempts} attempts)`);
}
/**
 * Launch Chrome browser with CDP enabled
 */
async function launchBrowser(config) {
    const chromePath = config.chromePath || getChromePath();
    const cdpPort = config.cdpPort;
    // Refuse to spawn when the CDP port already has a live endpoint: the new
    // Chrome could never bind it and would linger as an unmanaged headed window.
    // Callers catch CdpPortInUseError and adopt the existing instance instead.
    if (await isCdpEndpointReachable(cdpPort)) {
        throw new CdpPortInUseError(`CDP port ${cdpPort} already has a reachable browser instance`);
    }
    const runtimeChromeFlags = resolveRuntimeChromeFlags(config.chromeFlags || []);
    const runtimeHeadless = resolveHeadlessMode(config.headless);
    // Create a temporary user data directory if not provided
    const userDataDir = config.userDataDir
        || (0, path_1.join)((0, os_1.tmpdir)(), `chrome-cdp-${Date.now()}-${(0, crypto_1.randomBytes)(4).toString('hex')}`);
    if (!(0, fs_1.existsSync)(userDataDir)) {
        (0, fs_1.mkdirSync)(userDataDir, { recursive: true });
    }
    // Build Chrome arguments
    const args = [
        `--remote-debugging-port=${cdpPort}`,
        '--remote-debugging-address=127.0.0.1',
        `--user-data-dir=${userDataDir}`, // Always use isolated user data dir
        ...runtimeChromeFlags
    ];
    if (runtimeHeadless) {
        args.push('--headless=new');
    }
    console.log(`[Browser] Launching Chrome at: ${chromePath}`);
    console.log(`[Browser] CDP port: ${cdpPort}`);
    console.log(`[Browser] User data dir: ${userDataDir}`);
    console.log(`[Browser] Headless: ${runtimeHeadless}`);
    console.log(`[Browser] Flags: ${runtimeChromeFlags.join(' ') || '(none)'}`);
    // Spawn Chrome process
    const browserProcess = (0, child_process_1.spawn)(chromePath, args, {
        detached: false,
        stdio: ['ignore', 'pipe', 'pipe'] // Capture stdout and stderr
    });
    const recentStderr = [];
    // Log Chrome output for debugging
    if (browserProcess.stdout) {
        browserProcess.stdout.on('data', (data) => {
            console.log(`[Browser stdout] ${data.toString().trim()}`);
        });
    }
    if (browserProcess.stderr) {
        browserProcess.stderr.on('data', (data) => {
            const message = data.toString().trim();
            console.log(`[Browser stderr] ${message}`);
            if (!message) {
                return;
            }
            for (const line of message.split('\n').map((item) => item.trim()).filter(Boolean)) {
                recentStderr.push(line);
            }
            while (recentStderr.length > 12) {
                recentStderr.shift();
            }
        });
    }
    if (!browserProcess.pid) {
        throw new Error('Failed to start Chrome process');
    }
    console.log(`[Browser] Chrome started with PID: ${browserProcess.pid}`);
    // Wait for CDP to be ready, then confirm the endpoint belongs to this spawn.
    try {
        await waitForCDP(cdpPort, browserProcess, 20000); // Increased timeout to 20 seconds
        await verifySpawnOwnsCdpPort(cdpPort, browserProcess);
        console.log(`[Browser] CDP ready on port ${cdpPort}`);
    }
    catch (error) {
        await terminateSpawnedProcess(browserProcess);
        if (error instanceof CdpPortInUseError) {
            throw error;
        }
        const baseMessage = error instanceof Error ? error.message : String(error);
        if (recentStderr.length > 0) {
            const tail = recentStderr.slice(-5).join(' | ');
            throw new Error(`${baseMessage}. Recent browser stderr: ${tail}`);
        }
        throw error;
    }
    return {
        process: browserProcess,
        pid: browserProcess.pid,
        cdpPort,
        startTime: Date.now(),
        adopted: false
    };
}
/**
 * Close an adopted browser we have no process handle for by asking Chrome to
 * shut itself down over CDP.
 */
async function closeAdoptedBrowser(cdpPort) {
    console.log(`[Browser] Closing adopted browser via CDP (port: ${cdpPort})`);
    let browser;
    try {
        browser = await playwright_core_1.chromium.connectOverCDP(`http://127.0.0.1:${cdpPort}`, { timeout: 5000 });
    }
    catch {
        console.log('[Browser] Adopted browser CDP is unreachable, nothing to close');
        return;
    }
    try {
        const session = await browser.newBrowserCDPSession();
        await session.send('Browser.close');
    }
    catch (error) {
        // Browser.close tears the CDP connection down while the browser exits,
        // which can surface as a send error; log it for diagnostics only.
        console.warn(`[Browser] CDP Browser.close reported: ${error instanceof Error ? error.message : String(error)}`);
    }
    finally {
        try {
            await browser.close();
        }
        catch {
            // Connection is already gone when the browser exited.
        }
    }
    console.log('[Browser] Adopted browser closed');
}
function isPidAlive(pid) {
    try {
        process.kill(pid, 0);
        return true;
    }
    catch {
        return false;
    }
}
async function terminateProcessByPid(pid) {
    try {
        process.kill(pid, 'SIGTERM');
    }
    catch {
        return;
    }
    const deadline = Date.now() + 5000;
    while (Date.now() < deadline) {
        if (!isPidAlive(pid)) {
            return;
        }
        await new Promise(resolve => setTimeout(resolve, 200));
    }
    console.log(`[Browser] Force killing browser (PID: ${pid})`);
    try {
        process.kill(pid, 'SIGKILL');
    }
    catch {
        // Already gone.
    }
}
/**
 * Close browser instance
 */
async function closeBrowser(instance) {
    if (!instance.process) {
        if (!instance.adopted) {
            return;
        }
        await closeAdoptedBrowser(instance.cdpPort);
        if (instance.pid !== null && isPidAlive(instance.pid)) {
            // CDP close did not take effect; escalate via signals since we know the pid.
            console.warn(`[Browser] Adopted browser (PID: ${instance.pid}) survived CDP close, terminating by signal`);
            await terminateProcessByPid(instance.pid);
        }
        return;
    }
    console.log(`[Browser] Closing browser (PID: ${instance.pid})`);
    await terminateSpawnedProcess(instance.process);
    console.log(`[Browser] Browser closed`);
}
/**
 * Check if browser is running
 */
function isBrowserRunning(instance) {
    if (!instance) {
        return false;
    }
    if (!instance.process) {
        // Adopted instances have no process handle; CDP reachability decides liveness.
        return instance.adopted;
    }
    return !instance.process.killed;
}
//# sourceMappingURL=browser.js.map