-- ============================================================
-- get_site_controllers.sql
-- 
-- Fetches all ACM controllers registered to a given site.
-- The featureRollOutMapping join (FeatureRollOutId = 2) ensures
-- we only return ACM-enabled devices.
--
-- Parameter: site_name  e.g. 'Flowserve US Raleigh NC (US)'
-- ============================================================

SELECT
    d.SerialNumber,
    CAST(d.Id AS NVARCHAR)  AS DeviceId,
    d.DefaultConfigName     AS DeviceName,
    p.Name                  AS SiteName,
    p.Id                    AS PlantId,
    comp.Name               AS SystemName,
    ps.Name                 AS PlantSystemName
FROM dbo.Device d
INNER JOIN dbo.featureRollOutMapping fr
    ON  fr.DeviceId         = d.Id
    AND fr.FeatureRollOutId = 2
LEFT JOIN dbo.Plant p
    ON p.Id = d.PlantId
LEFT JOIN dbo.Component comp
    ON comp.Id = (
        SELECT TOP 1 dc.ComponentId
        FROM dbo.DeviceComponent dc
        WHERE dc.DeviceId = d.Id
    )
LEFT JOIN dbo.PlantSystem ps
    ON ps.Id = comp.PlantSystemId
WHERE d.ApplicationID  = 1
  AND d.Status         = 1
  AND d.SerialNumber   IS NOT NULL
  AND p.Name           = :site_name
ORDER BY d.SerialNumber;
