-- ============================================================
-- get_service_notes.sql
--
-- Fetches all service notes for a given site within a date
-- range. The Description column contains the full note text
-- (HTML + plain text mixed), including "Actions Completed"
-- sections written by field engineers after site visits.
--
-- Parameters:
--   site_name   e.g. 'Flowserve US Raleigh NC (US)'
--   start_date  e.g. '2026-05-01'
--   end_date    e.g. '2026-05-31'
-- ============================================================

SELECT
    plant.Name                   AS Location,
    vertex.Name                  AS ContextPoint,
    serviceNote.CreatedDateTime  AS CreatedDate,
    serviceNote.ModifiedDateTime AS ModifiedDate,
    serviceNote.[Description]    AS ServiceNote,
    statusDetail.Name            AS [Status]
FROM [ServiceNote].[ServiceNote] serviceNote
INNER JOIN [dbo].[Plant] plant
    ON plant.Id = serviceNote.PlantId
INNER JOIN [Context].[Vertex] vertex
    ON serviceNote.ContextPointId = vertex.Id
INNER JOIN [dbo].[Status] statusDetail
    ON statusDetail.Id = serviceNote.[Status]
WHERE plant.Status  = 1
  AND vertex.Status = 1
  AND plant.Name    = :site_name
  AND serviceNote.CreatedDateTime >= :start_date
  AND serviceNote.CreatedDateTime <  DATEADD(day, 1, CAST(:end_date AS DATE))
ORDER BY serviceNote.ModifiedDateTime DESC;
