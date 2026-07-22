-- ============================================================
-- get_ade_data.sql
--
-- Fetches ADE / MDE field test measurements for a given site
-- within a date range. This includes hand-measured values
-- entered by engineers on site visits:
--   - Free Residual Chlorine (FRC)
--   - pH
--   - Conductivity
--   - TBC / Dip Slide results
--   - Tagged Polymer
--   - Any other ADE parameters
--
-- Uses the Latest table to get the most recent value for each
-- parameter instance at the time of the template creation.
--
-- Parameters:
--   site_name   e.g. 'Flowserve US Raleigh NC (US)'
--   start_date  e.g. '2026-05-01'
--   end_date    e.g. '2026-05-31'
-- ============================================================

;WITH TemplatesWithMeasurements AS (
    SELECT DISTINCT
        G.Name                  AS Region,
        P.Name                  AS PlantName,
        UPL.PSRFullName,
        MT.Id                   AS TemplateId,
        MT.Name                 AS Template,
        BT.Name                 AS BillingType,
        mt.ContextVertexId,
        parm.Id                 AS TemplateParameterId,
        parm.Name               AS Parameter,
        L.value                 AS Value,
        v.Name                  AS ContextVertexName,
        cpi.Id                  AS ParameterInstanceId,
        MT.CreatedDateTime
    FROM dbo.MDETemplate MT
    INNER JOIN dbo.Plant P
        ON MT.PlantId = P.Id AND P.Status = 1
    INNER JOIN Context.Vertex V
        ON V.Id = MT.ContextVertexId AND V.Status = 1
    LEFT JOIN Context.Kind K
        ON K.ID = V.KindId AND K.Status = 1
    OUTER APPLY (
        SELECT DISTINCT TOP 1
            CONCAT(PUP.FirstName, ' ', PUP.LastName) PSRFullName,
            PUP.EmailId PrimarySalesRepEmailId
        FROM dbo.UserPlant UPL
        INNER JOIN DBO.UserProfile PUP
            ON UPL.Status = 1
            AND UPL.UserTypeId = 1
            AND PUP.UserId = UPL.UserId
            AND UPL.PlantId = MT.PlantId
        INNER JOIN DBO.[User] USR
            ON USR.Id = PUP.UserId AND USR.Status = 1
    ) UPL
    INNER JOIN dbo.TemplateParameter tp
        ON tp.TemplateId = mt.Id
        AND mt.PlantId IS NOT NULL
        AND tp.StatusId = 1
    INNER JOIN Unit.ParameterUnit pu
        ON pu.ParameterId = tp.UnitParameterId AND pu.Status = 1
    INNER JOIN Unit.Parameter parm
        ON parm.Id = pu.ParameterId AND parm.IsAdeParameter = 1
    INNER JOIN Context.ParameterInstance cpi
        ON cpi.VertexId = mt.ContextVertexId
        AND cpi.ParameterId = pu.ParameterId
        AND cpi.Status = 1
    INNER JOIN dbo.Latest L
        ON L.ParameterInstanceId = cpi.Id
    INNER JOIN Context.Vertex PV
        ON PV.LegacyId = P.Id AND PV.KindId = 1 AND V.Status = 1
    INNER JOIN Context.Edge E
        ON E.VertexId = PV.Id AND E.Status = 1
    INNER JOIN Context.Vertex CV
        ON CV.Id = E.ChildVertexId
        AND CV.KindId IN (100052, 100053)
        AND CV.Status = 1
    INNER JOIN dbo.ShipTo STO
        ON STO.VertexId = CV.Id AND STO.Status = 1
    INNER JOIN dbo.Country C
        ON C.Code = STO.CountryCode
    INNER JOIN dbo.Geo G
        ON G.ID = C.GeoId
    LEFT JOIN Container CON
        ON CON.ComponentId = v.LegacyId
    LEFT JOIN [Pricing].[BillingType] BT
        ON BT.Id = CON.BillingTypeId AND BT.Status = 1
    WHERE MT.IsPredefined = 0
      AND MT.StatusId     = 1
      AND P.Name          = :site_name
      AND MT.CreatedDateTime >= :start_date
      AND MT.CreatedDateTime <  DATEADD(day, 1, CAST(:end_date AS DATE))
)
SELECT *
FROM TemplatesWithMeasurements
ORDER BY CreatedDateTime DESC;
