const SHEET_NAME = 'ReviewQueue';
const SYNC_TOKEN_PROPERTY = 'AI_LINKEDIN_SYNC_TOKEN';
const SYNC_TOKEN_FALLBACK = '__AI_LINKEDIN_SYNC_TOKEN__';
const SYNC_TOKEN_PLACEHOLDER_VALUE = '__AI_LINKEDIN_SYNC_TOKEN__';
const REQUIRED_HEADERS = [
  'review_id',
  'draft_id',
  'draft_version',
  'content_hash',
  'topic_title',
  'recommendation',
  'political_risk',
  'draft_readiness',
  'draft_text',
  'source_notes',
  'media_notes',
  'token_hash',
  'expires_at',
  'token_used_at',
  'approval_status',
  'approval_action',
  'approval_notes',
  'approved_at',
  'created_at'
];
const DECISION_HEADERS = [
  'token_used_at',
  'approval_status',
  'approval_action',
  'approval_notes',
  'approved_at'
];
const ALLOWED_ACTIONS = [
  'approve_text_only',
  'approve_text_plus_media',
  'approve_text_reject_media',
  'needs_edits',
  'pick_different_topic',
  'save_for_later',
  'reject'
];

function doGet(e) {
  const params = e.parameter || {};
  const mode = params.mode || params.action || '';

  if (mode === 'health') {
    return jsonOutput_({
      ok: true,
      app: 'AI LinkedIn Approval Web App',
      sync_enabled: Boolean(syncToken_()),
      sheet_name: SHEET_NAME
    });
  }

  const rid = params.rid;
  const rawToken = params.token;

  if (!rid || !rawToken) {
    return HtmlService.createHtmlOutput(errorHtml_('Missing review parameters.'));
  }

  const validation = validateToken_(rid, rawToken);
  if (!validation.ok) {
    return HtmlService.createHtmlOutput(errorHtml_(validation.reason));
  }

  const review = getReview_(rid);
  if (!review) {
    return HtmlService.createHtmlOutput(errorHtml_('Review not found.'));
  }

  const template = HtmlService.createTemplateFromFile('Index');
  template.review = review;
  template.rid = rid;
  template.rawToken = rawToken;
  return template.evaluate().setTitle('Review AI LinkedIn Draft');
}

function doPost(e) {
  const request = parseRequest_(e);
  const mode = request.mode || request.api_action || '';

  try {
    if (mode === 'sync_queue') {
      return syncReviewQueue_(request);
    }
    if (mode === 'export_decisions') {
      return exportDecisions_(request);
    }
    return recordApproval_(request);
  } catch (err) {
    return jsonOutput_({ ok: false, error: err.message || String(err) });
  }
}

function parseRequest_(e) {
  const params = Object.assign({}, e.parameter || {});
  const postData = e.postData || {};
  const contents = postData.contents || '';
  const type = String(postData.type || '').toLowerCase();

  if (contents && type.indexOf('application/json') >= 0) {
    try {
      const parsed = JSON.parse(contents);
      return Object.assign(params, parsed || {});
    } catch (err) {
      throw new Error('Invalid JSON request body: ' + err.message);
    }
  }

  return params;
}

function recordApproval_(request) {
  const rid = request.rid;
  const rawToken = request.token;
  const action = request.action;
  const notes = request.notes || '';

  if (!rid || !rawToken || !action) {
    return ContentService.createTextOutput('Missing parameters').setMimeType(ContentService.MimeType.TEXT);
  }

  const validation = validateToken_(rid, rawToken);
  if (!validation.ok) {
    return HtmlService.createHtmlOutput(errorHtml_(validation.reason));
  }

  if (!isAllowedAction_(action)) {
    return HtmlService.createHtmlOutput(errorHtml_('Invalid action.'));
  }

  writeApproval_(rid, action, notes);
  return HtmlService.createHtmlOutput(
    '<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">' +
    '<style>body{font-family:Arial,sans-serif;margin:24px;line-height:1.5;color:#172033}.card{border:1px solid #cbd5e1;border-radius:8px;padding:18px;max-width:680px}.ok{color:#166534;font-weight:700}</style>' +
    '</head><body><div class="card"><h1 class="ok">Approval recorded</h1><p>Your decision was saved to the ReviewQueue background sheet.</p><p>No automatic post was published. Return to the AI LinkedIn Console and press Import Phone Decision.</p></div></body></html>'
  );
}

function syncReviewQueue_(request) {
  requireSync_(request);
  const csvContent = request.csv_content || request.csv || '';
  if (!csvContent) {
    throw new Error('csv_content is required.');
  }

  const incomingRows = Utilities.parseCsv(csvContent);
  if (!incomingRows.length) {
    throw new Error('Review queue CSV is empty.');
  }
  validateHeaderRow_(incomingRows[0]);

  const sheet = getSheet_();
  const existingRows = sheet.getDataRange().getValues();
  const mergedRows = mergeExistingDecisions_(incomingRows, existingRows);
  sheet.clearContents();
  sheet.getRange(1, 1, mergedRows.length, REQUIRED_HEADERS.length).setValues(
    mergedRows.map(function(row) {
      return padRow_(row);
    })
  );

  return jsonOutput_({
    ok: true,
    action: 'sync_queue',
    total_rows: Math.max(mergedRows.length - 1, 0),
    decision_rows: countDecisionRows_(mergedRows),
    sheet_name: SHEET_NAME
  });
}

function exportDecisions_(request) {
  requireSync_(request);
  const sheet = getSheet_();
  ensureHeaderRow_(sheet);
  const rows = sheet.getDataRange().getValues();
  validateHeaderRow_(rows[0]);

  return jsonOutput_({
    ok: true,
    action: 'export_decisions',
    total_rows: Math.max(rows.length - 1, 0),
    decision_rows: countDecisionRows_(rows),
    csv_content: reviewQueueCsv_(rows)
  });
}

function validateToken_(rid, rawToken) {
  try {
    const sheet = getSheet_();
    const data = sheet.getDataRange().getValues();
    if (data.length < 2) {
      return { ok: false, reason: 'Review queue is empty. Press Sync to Phone Approval in the AI LinkedIn Console.' };
    }

    const indexes = columnIndexes_(data[0]);

    for (let i = 1; i < data.length; i++) {
      if (String(data[i][indexes.review_id]) === String(rid)) {
        if (data[i][indexes.token_used_at]) {
          return { ok: false, reason: 'Token already used' };
        }
        if (new Date() > new Date(data[i][indexes.expires_at])) {
          return { ok: false, reason: 'Token expired' };
        }
        if (sha256Hex_(rawToken) !== data[i][indexes.token_hash]) {
          return { ok: false, reason: 'Invalid token' };
        }
        return { ok: true, reason: 'OK' };
      }
    }

    return { ok: false, reason: 'Review not found. Press Sync to Phone Approval in the AI LinkedIn Console.' };
  } catch (err) {
    return { ok: false, reason: err.message };
  }
}

function getReview_(rid) {
  const sheet = getSheet_();
  const data = sheet.getDataRange().getValues();
  const indexes = columnIndexes_(data[0]);

  for (let i = 1; i < data.length; i++) {
    if (String(data[i][indexes.review_id]) === String(rid)) {
      return {
        reviewId: data[i][indexes.review_id],
        topicTitle: data[i][indexes.topic_title],
        draftText: data[i][indexes.draft_text],
        sourceNotes: data[i][indexes.source_notes],
        mediaNotes: data[i][indexes.media_notes],
        recommendation: data[i][indexes.recommendation],
        politicalRisk: data[i][indexes.political_risk],
        draftReadiness: data[i][indexes.draft_readiness]
      };
    }
  }

  return null;
}

function writeApproval_(rid, action, notes) {
  const sheet = getSheet_();
  const data = sheet.getDataRange().getValues();
  const indexes = columnIndexes_(data[0]);
  const now = new Date();

  for (let i = 1; i < data.length; i++) {
    if (String(data[i][indexes.review_id]) === String(rid)) {
      sheet.getRange(i + 1, indexes.approval_status + 1).setValue('completed');
      sheet.getRange(i + 1, indexes.approval_action + 1).setValue(action);
      sheet.getRange(i + 1, indexes.approval_notes + 1).setValue(notes);
      sheet.getRange(i + 1, indexes.approved_at + 1).setValue(now);
      sheet.getRange(i + 1, indexes.token_used_at + 1).setValue(now);
      return;
    }
  }

  throw new Error('Review not found.');
}

function getSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
  ensureHeaderRow_(sheet);
  return sheet;
}

function ensureHeaderRow_(sheet) {
  const range = sheet.getDataRange();
  if (range.getNumRows() === 1 && range.getNumColumns() === 1 && !range.getValue()) {
    sheet.getRange(1, 1, 1, REQUIRED_HEADERS.length).setValues([REQUIRED_HEADERS]);
    return;
  }
  const values = range.getValues();
  if (!values.length || !values[0].filter(String).length) {
    sheet.getRange(1, 1, 1, REQUIRED_HEADERS.length).setValues([REQUIRED_HEADERS]);
  }
}

function validateHeaderRow_(headers) {
  const missing = REQUIRED_HEADERS.filter(function(header) {
    return headers.indexOf(header) < 0;
  });
  if (missing.length > 0) {
    throw new Error('ReviewQueue missing required columns: ' + missing.join(', '));
  }
}

function mergeExistingDecisions_(incomingRows, existingRows) {
  if (!existingRows || existingRows.length < 2) {
    return incomingRows;
  }

  const incomingIndexes = columnIndexes_(incomingRows[0]);
  let existingIndexes;
  try {
    existingIndexes = columnIndexes_(existingRows[0]);
  } catch (err) {
    return incomingRows;
  }

  const decisionsByReview = {};
  for (let i = 1; i < existingRows.length; i++) {
    const row = existingRows[i];
    const reviewId = String(row[existingIndexes.review_id] || '');
    const action = String(row[existingIndexes.approval_action] || '');
    const status = String(row[existingIndexes.approval_status] || '');
    if (reviewId && (action || status === 'completed')) {
      decisionsByReview[reviewId] = row;
    }
  }

  for (let j = 1; j < incomingRows.length; j++) {
    const incoming = incomingRows[j];
    const reviewId = String(incoming[incomingIndexes.review_id] || '');
    const decision = decisionsByReview[reviewId];
    if (!decision) {
      continue;
    }
    DECISION_HEADERS.forEach(function(header) {
      incoming[incomingIndexes[header]] = decision[existingIndexes[header]] || incoming[incomingIndexes[header]] || '';
    });
  }

  return incomingRows;
}

function padRow_(row) {
  const result = row.slice(0, REQUIRED_HEADERS.length);
  while (result.length < REQUIRED_HEADERS.length) {
    result.push('');
  }
  return result;
}

function reviewQueueCsv_(rows) {
  return rows.map(function(row) {
    return REQUIRED_HEADERS.map(function(_, index) {
      return csvEscape_(formatCell_(row[index]));
    }).join(',');
  }).join('\n') + '\n';
}

function countDecisionRows_(rows) {
  if (!rows || rows.length < 2) {
    return 0;
  }
  const indexes = columnIndexes_(rows[0]);
  let count = 0;
  for (let i = 1; i < rows.length; i++) {
    const action = String(rows[i][indexes.approval_action] || '');
    const status = String(rows[i][indexes.approval_status] || '');
    if (action || status === 'completed') {
      count += 1;
    }
  }
  return count;
}

function formatCell_(value) {
  if (value instanceof Date) {
    return value.toISOString();
  }
  if (value === null || value === undefined) {
    return '';
  }
  return String(value);
}

function csvEscape_(value) {
  const text = String(value || '');
  if (text.indexOf('"') >= 0 || text.indexOf(',') >= 0 || text.indexOf('\n') >= 0 || text.indexOf('\r') >= 0) {
    return '"' + text.replace(/"/g, '""') + '"';
  }
  return text;
}

function syncToken_() {
  const propertyToken = PropertiesService.getScriptProperties().getProperty(SYNC_TOKEN_PROPERTY);
  if (propertyToken) {
    return propertyToken;
  }
  if (SYNC_TOKEN_FALLBACK && SYNC_TOKEN_FALLBACK !== SYNC_TOKEN_PLACEHOLDER_VALUE) {
    return SYNC_TOKEN_FALLBACK;
  }
  return '';
}

function requireSync_(request) {
  const expected = syncToken_();
  if (!expected) {
    throw new Error('AI_LINKEDIN_SYNC_TOKEN is not configured in Script properties or Code.gs.');
  }
  const supplied = request.sync_token || '';
  if (String(supplied) !== String(expected)) {
    throw new Error('Invalid sync token.');
  }
}

function jsonOutput_(payload) {
  return ContentService.createTextOutput(JSON.stringify(payload)).setMimeType(ContentService.MimeType.JSON);
}

function errorHtml_(message) {
  return '<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">' +
    '<style>body{font-family:Arial,sans-serif;margin:24px;line-height:1.5;color:#172033}.card{border:1px solid #fecaca;background:#fff7f7;border-radius:8px;padding:18px;max-width:680px}.error{color:#991b1b;font-weight:700}</style>' +
    '</head><body><div class="card"><h1 class="error">Approval page needs attention</h1><p>' + String(message).replace(/[<>&"]/g, function(ch) {
      return {'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[ch];
    }) + '</p><p>Return to the AI LinkedIn Console and use the Approve tab.</p></div></body></html>';
}

function sha256Hex_(value) {
  const bytes = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, value, Utilities.Charset.UTF_8);
  return bytes.map(function(byte) {
    return ('0' + (byte & 0xFF).toString(16)).slice(-2);
  }).join('');
}

function isAllowedAction_(action) {
  return ALLOWED_ACTIONS.indexOf(action) >= 0;
}

function columnIndexes_(headers) {
  validateHeaderRow_(headers);
  const indexes = {};
  REQUIRED_HEADERS.forEach(function(header) {
    indexes[header] = headers.indexOf(header);
  });
  return indexes;
}
