ALTER TABLE document_version
  ADD COLUMN original_filename varchar(255);

UPDATE document_version v
   SET original_filename = d.original_filename
  FROM document_source d
 WHERE d.id = v.document_id;

ALTER TABLE document_version
  ALTER COLUMN original_filename SET NOT NULL;
