/* Lossless assembly of oversized transcript records for the ohflow dashboard.
 *
 * The transcript API ships a logical record larger than the inline cap as
 * several `ohflow.record-json/1` continuation rows: one envelope per response
 * page, all sharing the record's `id`, each carrying
 * `continuation: {record_id, offset, next_offset, total_chars, data,
 * complete}`.  Concatenating the `data` parts of one record in offset order
 * and JSON-decoding the join yields the complete normalized record.
 *
 * This module is pure data: no DOM, no fetch, no timers.  The dashboard keeps
 * one ledger per transcript; `absorb` consumes each response's rows, holds
 * unfinished fragments out of the logical stream, and slots a decoded record
 * into the placeholder its first fragment left.  Offsets are Unicode
 * code-point numbers supplied by the server, so ordering and coverage checks
 * never use JS string lengths (UTF-16 units), and completion comes from the
 * server's `complete` flag plus a gap-free 0..total chain - never from
 * counting characters client-side.
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.ohflowRecords = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var MAX_DIAGNOSTICS = 20;

  /* Normalize the two transcript result shapes once for every renderer:
   *
   * - block-level: a `tool_result` block carrying `call_id`
   * - record-level: a `tool_result` record carrying `tool_call_id`, whose
   *   text blocks are the result payload
   *
   * `blockIndexes` identifies only the payload blocks represented by the
   * normalized result. Callers can suppress those exact blocks after pairing
   * while leaving unrelated blocks in a mixed record visible. */
  function collectToolResults(records) {
    var results = new Map();
    (Array.isArray(records) ? records : []).forEach(function (record) {
      var blocks = Array.isArray(record && record.blocks) ? record.blocks : [];
      blocks.forEach(function (block, index) {
        if (!block || block.type !== "tool_result" || block.call_id == null) return;
        results.set(String(block.call_id), {
          block: block,
          record: record,
          blockIndexes: [index],
          shape: "block"
        });
      });
      if (!record || record.type !== "tool_result"
              || record.tool_call_id == null) return;
      var text = [];
      var indexes = [];
      blocks.forEach(function (block, index) {
        if (block && block.type === "text" && typeof block.text === "string") {
          text.push(block.text);
          indexes.push(index);
        }
      });
      if (!indexes.length) return;
      results.set(String(record.tool_call_id), {
        block: {
          type: "tool_result",
          call_id: String(record.tool_call_id),
          content: text.join(""),
          is_error: record.is_error === true || record.error != null
        },
        record: record,
        blockIndexes: indexes,
        shape: "record"
      });
    });
    return results;
  }

  function codePointLength(text) {
    return Array.from(text).length;
  }

  function createLedger() {
    var records = [];         /* logical records, in arrival order */
    var seen = new Map();     /* record id -> index in `records` */
    var pending = new Map();  /* record id -> assembly entry */
    var diagnostics = [];
    var noted = new Set();
    var logical = 0;

    function note(key, text) {
      if (noted.has(key) || diagnostics.length >= MAX_DIAGNOSTICS) return;
      noted.add(key);
      diagnostics.push(text);
    }

    /* A fragment of a record nobody has finished yet leaves an explicit
     * placeholder in the stream: visible, honestly labelled, and never
     * counted as a loaded record. */
    function placeholderFor(entry) {
      if (entry.at >= 0) {
        records[entry.at].parts = entry.parts.size;
        return;
      }
      entry.at = records.length;
      records.push({
        id: entry.id,
        continuing: true,
        parts: entry.parts.size,
        type: entry.sample.type,
        role: entry.sample.role,
        ts: entry.sample.ts,
        source: entry.sample.source
      });
    }

    /* The record is complete only when its parts cover 0..total_chars with no
     * gap (each part's server-supplied `next_offset` begins the next part),
     * and the final part says `complete` exactly at total_chars. */
    function chainCoverage(entry) {
      var offsets = Array.from(entry.parts.keys()).sort(function (a, b) {
        return a - b;
      });
      if (!offsets.length) return null;
      if (offsets[0] !== 0) {
        note("start:" + entry.id,
            "Record " + entry.id + " is missing continuation coverage from "
            + "character 0 to " + offsets[0] + "; it stays explicitly "
            + "incomplete until that coverage arrives.");
        return null;
      }
      var pieces = [];
      var last = null;
      for (var i = 0; i < offsets.length; i += 1) {
        var part = entry.parts.get(offsets[i]);
        if (last && last.next !== offsets[i]) {
          var relation = last.next < offsets[i] ? "missing" : "overlapping";
          note("gap:" + entry.id + ":" + last.next + ":" + offsets[i],
              "Record " + entry.id + " has " + relation
              + " continuation coverage between characters " + last.next
              + " and " + offsets[i] + "; it stays explicitly incomplete "
              + "until a valid gap-free chain arrives.");
          return null;
        }
        pieces.push(part.data);
        last = part;
      }
      if (!last || !last.complete) return null;
      if (entry.total === null || last.next !== entry.total) {
        note("tail:" + entry.id,
            "Record " + entry.id + " claims completion at character "
            + (last ? last.next : "unknown") + " but declares total_chars "
            + entry.total + "; it stays explicitly incomplete.");
        return null;
      }
      return pieces.join("");
    }

    function assemble(entry) {
      var text = chainCoverage(entry);
      if (text === null) return false;
      var decoded;
      try {
        decoded = JSON.parse(text);
      } catch (error) {
        note("parse:" + entry.id,
            "Record " + entry.id + " arrived whole but could not be decoded ("
            + error.message + "); it stays explicitly incomplete.");
        return false;
      }
      if (!decoded || typeof decoded !== "object"
              || (decoded.id != null && String(decoded.id) !== String(entry.id))) {
        note("shape:" + entry.id,
            "Record " + entry.id + " decoded to a different record; "
            + "it stays explicitly incomplete rather than mislabelled.");
        return false;
      }
      if (entry.at >= 0 && records[entry.at] && records[entry.at].continuing) {
        records[entry.at] = decoded;
      } else {
        entry.at = records.length;
        records.push(decoded);
      }
      seen.set(entry.id, entry.at);
      logical += 1;
      pending.delete(entry.id);
      return true;
    }

    function absorbFull(row) {
      var id = row.id != null ? String(row.id) : null;
      if (id === null) {
        records.push(row);
        logical += 1;
        return;
      }
      if (seen.has(id)) return;              /* duplicate row */
      var entry = pending.get(id);
      if (entry) {                           /* a whole record supersedes parts */
        pending.delete(id);
        if (entry.at >= 0 && records[entry.at] && records[entry.at].continuing) {
          records[entry.at] = row;
        } else {
          entry.at = records.length;
          records.push(row);
        }
        seen.set(id, entry.at);
        logical += 1;
        return;
      }
      seen.set(id, records.length);
      records.push(row);
      logical += 1;
    }

    function absorbFragment(row) {
      var cont = row.continuation;
      var id = cont.record_id != null ? String(cont.record_id)
          : (row.id != null ? String(row.id) : null);
      if (id === null || seen.has(id)) return null;
      var entry = pending.get(id);
      if (!entry) {
        entry = {
          id: id,
          parts: new Map(),
          at: -1,
          sample: row,
          total: null
        };
        pending.set(id, entry);
      }
      placeholderFor(entry);
      var offset = Number(cont.offset);
      var next = Number(cont.next_offset);
      var total = Number(cont.total_chars);
      var integers = Number.isInteger(offset) && Number.isInteger(next)
          && Number.isInteger(total);
      if (!integers || offset < 0 || next < offset || total < 0
              || offset > total || next > total) {
        note("range:" + id + ":" + cont.offset + ":" + cont.next_offset,
            "Record " + id + " has an invalid continuation range (offset "
            + cont.offset + ", next_offset " + cont.next_offset
            + ", total_chars " + cont.total_chars
            + "); the fragment was rejected.");
        return entry;
      }
      if (entry.total === null) entry.total = total;
      else if (entry.total !== total) {
        note("total:" + id + ":" + total,
            "Record " + id + " declares contradictory total_chars values "
            + entry.total + " and " + total + "; the conflicting fragment "
            + "was rejected.");
        return entry;
      }
      var data = typeof cont.data === "string" ? cont.data : "";
      var span = codePointLength(data);
      if (span !== next - offset) {
        note("span:" + id + ":" + offset,
            "Record " + id + " has " + span + " Unicode code points in the "
            + "fragment at character " + offset + " but its range spans "
            + (next - offset) + "; the fragment was rejected.");
        return entry;
      }
      if (cont.complete === true && next !== total) {
        note("early:" + id + ":" + next,
            "Record " + id + " claims completion at character " + next
            + " before total_chars " + total + "; the fragment was rejected.");
        return entry;
      }
      var part = {
        data: data,
        next: next,
        complete: cont.complete === true
      };
      var existing = entry.parts.get(offset);
      if (existing) {
        if (existing.data !== part.data || existing.next !== part.next
                || existing.complete !== part.complete) {
          note("duplicate:" + id + ":" + offset,
              "Record " + id + " delivered conflicting continuation parts "
              + "at character " + offset + "; the duplicate was rejected.");
        }
        return entry;
      }
      entry.parts.set(offset, part);
      placeholderFor(entry);
      return entry;
    }

    return {
      /* Consume one response page's rows. Rows may arrive in any order, may
       * repeat, and may interleave fragments of several records. */
      absorb: function (rows) {
        var before = logical;
        var touched = new Set();
        (Array.isArray(rows) ? rows : []).forEach(function (row) {
          if (!row || typeof row !== "object") return;
          if (row.continuation && typeof row.continuation === "object") {
            var entry = absorbFragment(row);
            if (entry) touched.add(entry);
          } else {
            absorbFull(row);
          }
        });
        touched.forEach(function (entry) {
          if (pending.get(entry.id) === entry) assemble(entry);
        });
        return { added: logical - before, records: records };
      },
      /* A source reset (truncation, replacement) invalidates every fragment
       * and record gathered so far. */
      reset: function () {
        records.length = 0;
        seen.clear();
        pending.clear();
        diagnostics.length = 0;
        noted.clear();
        logical = 0;
      },
      records: records,
      loadedCount: function () { return logical; },
      pendingCount: function () { return pending.size; },
      diagnostics: diagnostics
    };
  }

  return {
    createLedger: createLedger,
    collectToolResults: collectToolResults
  };
});
