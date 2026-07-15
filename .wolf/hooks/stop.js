import * as fs from "node:fs";
import * as path from "node:path";
import { getWolfDir, ensureWolfDir, readJSON, writeJSON, appendMarkdown, timeShort, countSemanticEntries, readStdin, readTranscriptUsage, detectAgent } from "./shared.js";
async function main() {
    ensureWolfDir();
    const wolfDir = getWolfDir();
    const hooksDir = path.join(wolfDir, "hooks");
    const sessionFile = path.join(hooksDir, "_session.json");
    // Stop payload → transcript path for real usage measurement (F1)
    let hookInput = {};
    try {
        hookInput = JSON.parse(await readStdin());
    }
    catch { }
    const session = readJSON(sessionFile, {
        session_id: "",
        started: "",
        files_read: {},
        files_written: [],
        edit_counts: {},
        anatomy_hits: 0,
        anatomy_misses: 0,
        repeated_reads_warned: 0,
        cerebrum_warnings: 0,
        stop_count: 0,
    });
    session.stop_count++;
    // Only write to ledger if there's been activity
    const readCount = Object.keys(session.files_read).length;
    const writeCount = session.files_written.length;
    if (readCount === 0 && writeCount === 0) {
        writeJSON(sessionFile, session);
        process.exit(0);
        return;
    }
    // Collect end-of-turn reminders — returned as strings, then surfaced via additionalContext
    const reminders = [
        checkForMissingBugLogs(wolfDir, session),
        checkCerebrumFreshness(wolfDir, session),
        checkSemanticSummaries(wolfDir, session),
    ].filter((r) => r !== null);
    // Check if STATUS.md is stale relative to this session
    checkStatusFreshness(wolfDir, session);
    // Build session entry for ledger
    const reads = Object.entries(session.files_read).map(([file, data]) => ({
        file,
        tokens_estimated: data.tokens,
        was_repeated: data.count > 1,
        anatomy_had_description: false, // simplified
    }));
    const writes = session.files_written.map((w) => ({
        file: w.file,
        tokens_estimated: w.tokens,
        action: w.action,
    }));
    const inputTokens = reads.reduce((sum, r) => sum + r.tokens_estimated, 0);
    const outputTokens = writes.reduce((sum, w) => sum + w.tokens_estimated, 0);
    const sessionEntry = {
        id: session.session_id,
        agent: detectAgent(),
        started: session.started,
        ended: new Date().toISOString(),
        reads,
        writes,
        totals: {
            input_tokens_estimated: inputTokens,
            output_tokens_estimated: outputTokens,
            reads_count: readCount,
            writes_count: writeCount,
            repeated_reads_blocked: session.repeated_reads_warned,
            anatomy_lookups: session.anatomy_hits,
        },
    };
    // Update token-ledger.json
    const ledgerPath = path.join(wolfDir, "token-ledger.json");
    const ledger = readJSON(ledgerPath, {
        version: 1,
        created_at: "",
        lifetime: {
            total_tokens_estimated: 0,
            total_reads: 0,
            total_writes: 0,
            total_sessions: 0,
            anatomy_hits: 0,
            anatomy_misses: 0,
            repeated_reads_blocked: 0,
            estimated_savings_vs_bare_cli: 0,
        },
        sessions: [],
        daemon_usage: [],
        waste_flags: [],
        optimization_report: { last_generated: null, patterns: [] },
    });
    // Attach measured usage from the transcript when the harness provides it.
    if (hookInput.transcript_path) {
        const real = readTranscriptUsage(hookInput.transcript_path);
        if (real) {
            sessionEntry.real_usage = real;
            const lt = ledger.lifetime;
            lt.real_input_tokens = (lt.real_input_tokens ?? 0) + real.input_tokens;
            lt.real_output_tokens = (lt.real_output_tokens ?? 0) + real.output_tokens;
            lt.real_cache_read_tokens = (lt.real_cache_read_tokens ?? 0) + real.cache_read_input_tokens;
            lt.real_cache_creation_tokens = (lt.real_cache_creation_tokens ?? 0) + real.cache_creation_input_tokens;
            lt.real_api_calls = (lt.real_api_calls ?? 0) + real.api_calls;
        }
    }
    ledger.sessions.push(sessionEntry);
    ledger.lifetime.total_reads += readCount;
    ledger.lifetime.total_writes += writeCount;
    ledger.lifetime.total_tokens_estimated += inputTokens + outputTokens;
    ledger.lifetime.anatomy_hits += session.anatomy_hits;
    ledger.lifetime.anatomy_misses += session.anatomy_misses;
    ledger.lifetime.repeated_reads_blocked += session.repeated_reads_warned;
    // Estimate savings: anatomy hits save ~200 tokens each, repeated reads blocked save their token count
    const savedFromAnatomy = session.anatomy_hits * 200;
    const savedFromRepeats = Object.values(session.files_read)
        .filter((r) => r.count > 1)
        .reduce((sum, r) => sum + r.tokens * (r.count - 1), 0);
    ledger.lifetime.estimated_savings_vs_bare_cli += savedFromAnatomy + savedFromRepeats;
    writeJSON(ledgerPath, ledger);
    // Write a session summary line to memory.md if there was meaningful activity
    if (writeCount > 0) {
        try {
            const uniqueFiles = new Set(session.files_written.map(w => path.basename(w.file)));
            const fileList = [...uniqueFiles].slice(0, 5).join(", ");
            const memoryPath = path.join(wolfDir, "memory.md");
            appendMarkdown(memoryPath, `| ${timeShort()} | Session end: ${writeCount} writes across ${uniqueFiles.size} files (${fileList}) | ${readCount} reads | ~${inputTokens + outputTokens} tok |\n`);
        }
        catch { }
    }
    writeJSON(sessionFile, session);
    // Surface reminders via additionalContext so they appear in Claude's next context window.
    // Using process.stdout JSON is the only reliable way for Stop hooks to inject content
    // into Claude Code's context — process.stderr output goes to the terminal only.
    if (reminders.length > 0) {
        const additionalContext = `⚠️ OpenWolf end-of-turn reminders:\n${reminders.map(r => `• ${r}`).join("\n")}`;
        process.stdout.write(JSON.stringify({ hookSpecificOutput: { hookEventName: "Stop", additionalContext } }));
    }
    process.exit(0);
}
/**
 * Check if files were edited multiple times but buglog.json wasn't updated.
 * Returns a reminder string if action is needed, otherwise null.
 */
function checkForMissingBugLogs(wolfDir, session) {
    if (!session.edit_counts)
        return null;
    const multiEditFiles = Object.entries(session.edit_counts)
        .filter(([, count]) => count >= 3)
        .map(([file]) => path.basename(file));
    if (multiEditFiles.length === 0)
        return null;
    // files_written only records writes made through the Edit/Write tools
    // (recorded by post-write.js's PostToolUse hook) -- a buglog.json update
    // made via Bash (e.g. a python -c json.dump one-liner, or any shell
    // redirection) never appears there, so this check used to nag forever
    // even after the bug was correctly logged. Fall back to the file's mtime
    // vs session start, same pattern checkStatusFreshness already uses for
    // STATUS.md, which catches a buglog.json write regardless of which tool
    // made it.
    const buglogWritten = session.files_written.some(w => w.file.includes("buglog.json"));
    if (buglogWritten)
        return null;
    const buglogPath = path.join(wolfDir, "buglog.json");
    try {
        const stat = fs.statSync(buglogPath);
        const sessionStartMs = session.started ? Date.parse(session.started) : 0;
        if (sessionStartMs && stat.mtimeMs >= sessionStartMs) {
            return null;
        }
    }
    catch {
        // buglog.json doesn't exist -- fall through to the reminder below.
    }
    return `ACTION REQUIRED: Files edited 3+ times this session (${multiEditFiles.join(", ")}) but buglog.json was not updated. Log the bug fixes to .wolf/buglog.json now.`;
}
/**
 * Check if STATUS.md is older than the session start AND there was meaningful
 * code activity (3+ writes outside .wolf/). If so, nudge Claude to update
 * STATUS.md so the next /clear has fresh handoff context.
 */
function checkStatusFreshness(wolfDir, session) {
    const statusPath = path.join(wolfDir, "STATUS.md");
    const codeWrites = session.files_written.filter((w) => !w.file.includes("/.wolf/") && !w.file.endsWith(".tmp"));
    try {
        const stat = fs.statSync(statusPath);
        const sessionStartMs = session.started ? Date.parse(session.started) : 0;
        if (!sessionStartMs)
            return;
        if (codeWrites.length >= 3 && stat.mtimeMs < sessionStartMs) {
            process.stderr.write(`📌 OpenWolf: STATUS.md not updated this session despite ${codeWrites.length} code writes. Update .wolf/STATUS.md (✅ done / 🚀 next quest) before /clear so next session resumes in 1 read.\n`);
        }
    }
    catch {
        // STATUS.md doesn't exist — nudge to create it if there were code writes
        if (codeWrites.length >= 3) {
            process.stderr.write(`📌 OpenWolf: .wolf/STATUS.md missing. Create it with current quest summary + next steps so /clear stays cheap.\n`);
        }
    }
}
/**
 * Check if cerebrum.md was updated recently. If it hasn't been updated in
 * a while and there was significant activity, return a reminder.
 */
function checkCerebrumFreshness(wolfDir, session) {
    const cerebrumPath = path.join(wolfDir, "cerebrum.md");
    try {
        const stat = fs.statSync(cerebrumPath);
        const hoursSinceUpdate = (Date.now() - stat.mtimeMs) / (1000 * 60 * 60);
        if (hoursSinceUpdate > 24 && session.files_written.length >= 3) {
            return `ACTION REQUIRED: cerebrum.md hasn't been updated in ${Math.floor(hoursSinceUpdate)}h and ${session.files_written.length} files were modified. Update .wolf/cerebrum.md with any new user preferences, conventions, or gotchas discovered this session.`;
        }
    }
    catch {
        // cerebrum.md doesn't exist, that's ok
    }
    return null;
}
/**
 * Check if a semantic summary was written to memory.md this session.
 * Returns a reminder string if action is needed, otherwise null.
 */
function checkSemanticSummaries(wolfDir, session) {
    const writeCount = session.files_written.length;
    if (writeCount < 2)
        return null;
    const semanticCount = countSemanticEntries(wolfDir);
    if (semanticCount === 0) {
        return `ACTION REQUIRED: ${writeCount} files were modified this session but no semantic summary was written to memory.md. Append a one-line summary: | HH:MM | description | file(s) | outcome | ~tokens |`;
    }
    return null;
}
// Run only when executed as a hook script — never on import (tests import
// readTranscriptUsage, and main() exits the process).
import { pathToFileURL } from "node:url";
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
    main().catch(() => process.exit(0));
}
//# sourceMappingURL=stop.js.map