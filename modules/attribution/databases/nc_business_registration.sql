-- North Carolina Secretary of State, Business Registration bulk export dictionary.
-- https://www.sosnc.gov/documents/forms/Data_Subcriptions/Business_Registration_layout.pdf
-- Complete snapshot layout, including the June 2015 pending-filings revision.
-- SQLite TEXT preserves source dates and identifiers that can contain leading zeroes.
-- Entities and ProfileItems are referenced in the dictionary but are not exported.
BEGIN;

CREATE TABLE Names (
    ENameID INTEGER PRIMARY KEY,
    EntityID INTEGER NOT NULL,
    EName TEXT NOT NULL,
    NTypeID INTEGER,
    Prefix TEXT,
    LastName TEXT,
    MiddleName TEXT,
    FirstName TEXT,
    Suffix TEXT,
    OldStatus TEXT
) WITHOUT ROWID;

CREATE TABLE NameTypes (
    NTypeID INTEGER PRIMARY KEY,
    NTypeName TEXT
) WITHOUT ROWID;

CREATE TABLE Addresses (
    AddressID INTEGER PRIMARY KEY,
    EntityID INTEGER,
    ATypeId INTEGER,
    Addr1 TEXT,
    Addr2 TEXT,
    Addr3 TEXT,
    City TEXT,
    State TEXT,
    Zip TEXT,
    CountyName TEXT,
    Country TEXT
) WITHOUT ROWID;

CREATE TABLE AddressTypes (
    ATypeId INTEGER PRIMARY KEY,
    ATypeName TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE Corporations (
    PItemId INTEGER PRIMARY KEY,
    EntityID INTEGER NOT NULL,
    OfficeAddressID INTEGER,
    OfficeMailingID INTEGER,
    AgentEntityID INTEGER,
    CorpType TEXT NOT NULL,
    CorpNum TEXT NOT NULL,
    Status INTEGER NOT NULL,
    Citzenship TEXT NOT NULL,
    DateFormed TEXT,
    DisolveDate TEXT,
    Duration TEXT,
    CountyOfInc TEXT,
    CountyFileNum TEXT,
    StateOfInc TEXT,
    CountryOfInc TEXT,
    Purpose TEXT,
    Profession TEXT,
    Managed INTEGER,
    Members INTEGER,
    Directors INTEGER,
    MemberManaged INTEGER,
    FiscalMonth INTEGER,
    AnnualRptDueDate TEXT,
    OldStatus TEXT
) WITHOUT ROWID;

CREATE TABLE CorpStatus (
    Status INTEGER PRIMARY KEY,
    StatusDesc TEXT NOT NULL,
    OldStatus TEXT
) WITHOUT ROWID;

CREATE TABLE Filings (
    EventLogID INTEGER PRIMARY KEY,
    PItemId INTEGER NOT NULL,
    DocumentID TEXT,
    DocumentType TEXT,
    FilingDate TEXT,
    EffectiveDate TEXT
) WITHOUT ROWID;

CREATE TABLE PendingFilings (
    EventLogID INTEGER PRIMARY KEY,
    PItemId INTEGER NOT NULL,
    DocumentID TEXT,
    DocumentType TEXT,
    FilingDate TEXT,
    EffectiveDate TEXT
) WITHOUT ROWID;

CREATE TABLE Stock (
    StockID INTEGER PRIMARY KEY,
    PItemId INTEGER NOT NULL,
    Created TEXT,
    Class TEXT,
    Shares REAL,
    NoParValue INTEGER,
    ParValue REAL
) WITHOUT ROWID;

CREATE TABLE NameReservations (
    EntityID INTEGER PRIMARY KEY,
    DocumentID TEXT,
    DocumentType TEXT,
    FilingDate TEXT,
    ExpirationDate TEXT,
    StateOfInc TEXT,
    CountryOfInc TEXT
) WITHOUT ROWID;

CREATE TABLE Officers (PItemID INTEGER NOT NULL, EntityID INTEGER NOT NULL);
CREATE TABLE Partners (PItemID INTEGER NOT NULL, EntityID INTEGER NOT NULL);
CREATE TABLE Directors (PItemID INTEGER NOT NULL, EntityID INTEGER NOT NULL);

CREATE TABLE CorpOfficers (
    PitemId INTEGER,
    Title TEXT,
    EntityTypeId INTEGER,
    Ename TEXT,
    Prefix TEXT,
    FirstName TEXT,
    MiddleName TEXT,
    LastName TEXT,
    Suffix TEXT,
    Addr1 TEXT,
    Addr2 TEXT,
    Addr3 TEXT,
    City TEXT,
    State TEXT,
    Zip TEXT
);

CREATE TABLE EntityTypes (
    ETypeId INTEGER PRIMARY KEY,
    Desctription TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE DocTypes (Abbreviation TEXT, Description TEXT);
CREATE TABLE CitizenshipTypes (Citzenship TEXT, Description TEXT);
CREATE TABLE CorpTypes (CorpType TEXT, Description TEXT);

CREATE INDEX names_entity_type ON Names(EntityID, NTypeID);
CREATE INDEX names_legal_lookup ON Names(EName COLLATE NOCASE) WHERE NTypeID = 1;
CREATE INDEX corporations_entity ON Corporations(EntityID);
CREATE INDEX corporations_number ON Corporations(CorpNum);
CREATE INDEX addresses_entity_type ON Addresses(EntityID, ATypeId);
CREATE INDEX corporate_officers_profile ON CorpOfficers(PitemId);

COMMIT;
