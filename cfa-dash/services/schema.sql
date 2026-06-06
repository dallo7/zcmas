PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS companies (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  pacra_number TEXT,
  tpin TEXT,
  zra_licence TEXT,
  zaffa_number TEXT,
  year_established TEXT,
  employee_count TEXT,
  company_email TEXT,
  phone TEXT,
  whatsapp TEXT,
  address_line1 TEXT,
  address_line2 TEXT,
  city TEXT,
  province TEXT,
  postal_address TEXT,
  bank_name TEXT,
  account_number TEXT,
  account_holder TEXT,
  branch TEXT,
  logo_path TEXT,
  status TEXT NOT NULL DEFAULT 'PENDING_APPROVAL',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  approved_at TEXT
);

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL,
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  username TEXT UNIQUE,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT,
  password_salt TEXT,
  must_change_password INTEGER NOT NULL DEFAULT 0,
  password_changed_at TEXT,
  phone TEXT,
  whatsapp TEXT,
  role TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS certificates (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL,
  name TEXT NOT NULL,
  file_name TEXT,
  file_url TEXT,
  uploaded_by TEXT,
  uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS bills_of_lading (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL,
  bl_number TEXT NOT NULL UNIQUE,
  doc_type TEXT NOT NULL,
  route_type TEXT NOT NULL,
  transport_mode TEXT NOT NULL,
  zra_regime TEXT NOT NULL,
  bl_type TEXT,
  currency TEXT,
  agent_license TEXT,
  company_name TEXT,
  consignor_tin TEXT,
  declarant_number TEXT,
  consignment_value REAL,
  shipper_name TEXT,
  shipper_address TEXT,
  shipper_country TEXT,
  carrier_name TEXT,
  vessel_vehicle_no TEXT,
  origin TEXT,
  destination TEXT,
  consignee_tin TEXT,
  consignee_name TEXT,
  gross_weight REAL DEFAULT 0,
  no_containers INTEGER DEFAULT 0,
  gn83_unit TEXT,
  gn83_fee_usd REAL,
  file_name TEXT,
  status TEXT NOT NULL DEFAULT 'UPLOADED',
  uploaded_by TEXT,
  uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reviewed_at TEXT,
  FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS containers (
  id TEXT PRIMARY KEY,
  bl_id TEXT NOT NULL,
  container_no TEXT,
  size TEXT,
  seal_no TEXT,
  FOREIGN KEY(bl_id) REFERENCES bills_of_lading(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cargo_items (
  id TEXT PRIMARY KEY,
  bl_id TEXT NOT NULL,
  container_id TEXT,
  description TEXT NOT NULL,
  hs_code TEXT,
  quantity REAL DEFAULT 1,
  unit TEXT,
  weight REAL DEFAULT 0,
  transport_mode TEXT,
  gn83_category TEXT NOT NULL,
  min_fee_usd REAL NOT NULL DEFAULT 0,
  FOREIGN KEY(bl_id) REFERENCES bills_of_lading(id) ON DELETE CASCADE,
  FOREIGN KEY(container_id) REFERENCES containers(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS reviewed_bls (
  id TEXT PRIMARY KEY,
  bl_id TEXT NOT NULL UNIQUE,
  z_sad_id TEXT,
  status TEXT NOT NULL DEFAULT 'REVIEWED',
  reviewed_by TEXT,
  reviewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  is_editable INTEGER NOT NULL DEFAULT 1,
  FOREIGN KEY(bl_id) REFERENCES bills_of_lading(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS z_sads (
  id TEXT PRIMARY KEY,
  reviewed_bl_id TEXT NOT NULL,
  bl_id TEXT NOT NULL,
  z_sad_number TEXT NOT NULL UNIQUE,
  generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  is_active INTEGER NOT NULL DEFAULT 1,
  is_used INTEGER NOT NULL DEFAULT 0,
  deactivated_at TEXT,
  FOREIGN KEY(reviewed_bl_id) REFERENCES reviewed_bls(id) ON DELETE CASCADE,
  FOREIGN KEY(bl_id) REFERENCES bills_of_lading(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS invoices (
  id TEXT PRIMARY KEY,
  reviewed_bl_id TEXT NOT NULL,
  z_sad_id TEXT NOT NULL,
  invoice_number TEXT NOT NULL UNIQUE,
  invoice_type TEXT NOT NULL,
  std_min_fee REAL NOT NULL,
  admin_fee REAL NOT NULL,
  vat REAL NOT NULL,
  total REAL NOT NULL,
  payable_amount REAL,
  contact_phone TEXT,
  contact_email TEXT,
  beneficiary_name TEXT,
  beneficiary_bank_name TEXT,
  beneficiary_account_number TEXT,
  status TEXT NOT NULL DEFAULT 'DRAFT',
  capitalpay_urn TEXT,
  checkout_url TEXT,
  pdf_path TEXT,
  due_date TEXT,
  signed_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(reviewed_bl_id) REFERENCES reviewed_bls(id) ON DELETE CASCADE,
  FOREIGN KEY(z_sad_id) REFERENCES z_sads(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS payments (
  id TEXT PRIMARY KEY,
  invoice_id TEXT NOT NULL,
  payment_type TEXT NOT NULL,
  amount REAL NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD',
  status TEXT NOT NULL DEFAULT 'PENDING',
  capitalpay_ref TEXT,
  secure_link TEXT,
  settled_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS contracts (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL,
  contract_no TEXT NOT NULL UNIQUE,
  importer_name TEXT NOT NULL,
  importer_phone TEXT,
  importer_email TEXT,
  terms TEXT,
  shipment_details TEXT,
  services TEXT,
  fees TEXT,
  qr_url TEXT,
  otp_hash TEXT,
  otp_salt TEXT,
  otp_sent_at TEXT,
  sent_at TEXT,
  status TEXT NOT NULL DEFAULT 'DRAFT',
  signed_email TEXT,
  signed_by TEXT,
  signature_name TEXT,
  signature_text TEXT,
  signature_file_path TEXT,
  contract_hash TEXT,
  signed_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notifications (
  id TEXT PRIMARY KEY,
  company_id TEXT,
  user_id TEXT,
  event_type TEXT NOT NULL,
  message TEXT NOT NULL,
  related_entity_id TEXT,
  is_read INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS support_tickets (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL,
  subject TEXT NOT NULL,
  description TEXT,
  linked_module TEXT,
  priority TEXT NOT NULL DEFAULT 'Medium',
  status TEXT NOT NULL DEFAULT 'Open',
  created_by TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at TEXT,
  FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_events (
  id TEXT PRIMARY KEY,
  company_id TEXT,
  user_id TEXT,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  mode TEXT,
  quality TEXT NOT NULL DEFAULT 'Neutral Response',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE SET NULL,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY,
  company_id TEXT,
  user_id TEXT,
  action_type TEXT NOT NULL,
  entity_type TEXT,
  entity_id TEXT,
  details TEXT,
  ip_address TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_sessions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  session_token TEXT NOT NULL UNIQUE,
  ip_address TEXT,
  user_agent TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TEXT NOT NULL,
  revoked_at TEXT,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(session_token);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id);

CREATE TABLE IF NOT EXISTS login_events (
  id TEXT PRIMARY KEY,
  user_id TEXT,
  email TEXT,
  success INTEGER NOT NULL DEFAULT 0,
  ip_address TEXT,
  user_agent TEXT,
  failure_reason TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_login_events_created ON login_events(created_at DESC);

CREATE TABLE IF NOT EXISTS registration_link_events (
  id TEXT PRIMARY KEY,
  user_id TEXT,
  email TEXT,
  source TEXT,
  ip_address TEXT,
  user_agent TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_registration_link_events_created ON registration_link_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_registration_link_events_user ON registration_link_events(user_id);

CREATE TABLE IF NOT EXISTS settlement_runs (
  id TEXT PRIMARY KEY,
  run_key TEXT NOT NULL UNIQUE,
  run_number TEXT NOT NULL,
  prepared_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  total_amount_tzs REAL NOT NULL DEFAULT 0,
  cfa_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'PREPARED'
);

CREATE TABLE IF NOT EXISTS settlement_run_items (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  company_id TEXT,
  cfa_company_name TEXT NOT NULL,
  cfa_licence_number TEXT,
  bank_name TEXT,
  bank_branch TEXT,
  bank_account_number TEXT,
  amount_tzs REAL NOT NULL DEFAULT 0,
  declarations_count INTEGER NOT NULL DEFAULT 0,
  payment_status TEXT NOT NULL DEFAULT 'Pending',
  capitalpay_reference TEXT,
  flag_reason TEXT,
  last_updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(run_id, company_id),
  FOREIGN KEY(run_id) REFERENCES settlement_runs(id) ON DELETE CASCADE,
  FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_settlement_run_items_run ON settlement_run_items(run_id);
CREATE INDEX IF NOT EXISTS idx_settlement_run_items_status ON settlement_run_items(payment_status);

CREATE TABLE IF NOT EXISTS settlement_download_logs (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  user_id TEXT,
  user_email TEXT,
  file_name TEXT NOT NULL,
  cfa_count INTEGER NOT NULL DEFAULT 0,
  total_amount_tzs REAL NOT NULL DEFAULT 0,
  downloaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(run_id) REFERENCES settlement_runs(id) ON DELETE CASCADE,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_settlement_download_logs_run ON settlement_download_logs(run_id);
CREATE INDEX IF NOT EXISTS idx_settlement_download_logs_downloaded ON settlement_download_logs(downloaded_at DESC);
