const HEADER_ABS = ['timestamp','session_id','mode','q','prompt_id','method','helpfulness','harmlessness','prompt','response','user_agent','locale'];
const HEADER_PAIR = ['timestamp','session_id','mode','q','prompt_id','method_a','method_b','helpfulness_pref','harmlessness_pref','prompt','response_a','response_b','user_agent','locale'];

function ensureSheet(name, header) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(name);
  if (!sh) sh = ss.insertSheet(name);
  if (sh.getLastRow() === 0) sh.appendRow(header);
  return sh;
}

function doPost(e) {
  try {
    const data = JSON.parse(e.parameter.data);
    const mode = data.mode;
    let sheet, rows;
    if (mode === 'absolute') {
      sheet = ensureSheet('Absolute', HEADER_ABS);
      rows = (data.answers || []).map(function(a) {
        return [data.timestamp, data.session_id, mode, a.q, a.prompt_id, a.method, a.helpfulness, a.harmlessness, a.prompt, a.response, data.user_agent, data.locale];
      });
    } else if (mode === 'pairwise') {
      sheet = ensureSheet('Pairwise', HEADER_PAIR);
      rows = (data.answers || []).map(function(a) {
        return [data.timestamp, data.session_id, mode, a.q, a.prompt_id, a.method_a, a.method_b, a.helpfulness_pref, a.harmlessness_pref, a.prompt, a.response_a, a.response_b, data.user_agent, data.locale];
      });
    } else {
      throw new Error('unknown mode: ' + mode);
    }
    if (rows.length) {
      sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, rows[0].length).setValues(rows);
    }
    return ContentService.createTextOutput(JSON.stringify({ ok: true, sheet: sheet.getName(), rows: rows.length })).setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ ok: false, error: String(err) })).setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet() {
  return ContentService.createTextOutput('Eval endpoint live (absolute + pairwise).');
}
