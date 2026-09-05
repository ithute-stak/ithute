CREATE TABLE domains (
  id SERIAL PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  master VARCHAR(128) DEFAULT NULL,
  last_check INTEGER DEFAULT NULL,
  type VARCHAR(8) NOT NULL,
  notified_serial BIGINT DEFAULT NULL,
  account VARCHAR(40) DEFAULT NULL,
  options TEXT DEFAULT NULL,
  catalog VARCHAR(255) DEFAULT NULL,
  CONSTRAINT uq_pdns_domains_name UNIQUE (name)
);
CREATE INDEX ix_pdns_domains_catalog ON domains(catalog);

CREATE TABLE records (
  id BIGSERIAL PRIMARY KEY,
  domain_id INTEGER DEFAULT NULL REFERENCES domains(id) ON DELETE CASCADE,
  name VARCHAR(255) DEFAULT NULL,
  type VARCHAR(10) DEFAULT NULL,
  content VARCHAR(65535) DEFAULT NULL,
  ttl INTEGER DEFAULT NULL,
  prio INTEGER DEFAULT NULL,
  disabled BOOLEAN DEFAULT FALSE,
  ordername VARCHAR(255),
  auth BOOLEAN DEFAULT TRUE
);
CREATE INDEX ix_pdns_records_name_type ON records(name,type);
CREATE INDEX ix_pdns_records_domain_id ON records(domain_id);
CREATE INDEX ix_pdns_records_ordername ON records(ordername);

CREATE TABLE supermasters (ip INET NOT NULL, nameserver VARCHAR(255) NOT NULL, account VARCHAR(40) NOT NULL, PRIMARY KEY(ip,nameserver));
CREATE TABLE comments (id SERIAL PRIMARY KEY, domain_id INTEGER NOT NULL REFERENCES domains(id) ON DELETE CASCADE, name VARCHAR(255) NOT NULL, type VARCHAR(10) NOT NULL, modified_at INTEGER NOT NULL, account VARCHAR(40) DEFAULT NULL, comment VARCHAR(65535) NOT NULL);
CREATE INDEX ix_pdns_comments_name_type ON comments(name,type);
CREATE INDEX ix_pdns_comments_domain_id ON comments(domain_id);
CREATE TABLE domainmetadata (id SERIAL PRIMARY KEY, domain_id INTEGER REFERENCES domains(id) ON DELETE CASCADE, kind VARCHAR(32), content TEXT);
CREATE INDEX ix_pdns_domainmetadata_domain_id ON domainmetadata(domain_id);
CREATE TABLE cryptokeys (id SERIAL PRIMARY KEY, domain_id INTEGER REFERENCES domains(id) ON DELETE CASCADE, flags INTEGER NOT NULL, active BOOLEAN, published BOOLEAN DEFAULT TRUE, content TEXT);
CREATE INDEX ix_pdns_cryptokeys_domain_id ON cryptokeys(domain_id);
CREATE TABLE tsigkeys (id SERIAL PRIMARY KEY, name VARCHAR(255), algorithm VARCHAR(50), secret VARCHAR(255));
CREATE UNIQUE INDEX uq_pdns_tsigkeys_name_algorithm ON tsigkeys(name, algorithm);
