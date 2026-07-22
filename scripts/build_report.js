const fs = require("fs");
const path = require("path");
const {
  AlignmentType,
  BorderStyle,
  Document,
  Footer,
  Header,
  HeadingLevel,
  Packer,
  PageBreak,
  PageNumber,
  Paragraph,
  ShadingType,
  Table,
  TableCell,
  TableRow,
  TextRun,
  VerticalAlign,
  WidthType,
} = require("docx");

const BUCKMAN_GREEN = "00857C";
const DARK_TEXT = "1F2933";
const MUTED_TEXT = "52606D";
const LIGHT_GREEN = "DFF3F1";
const LIGHT_GRAY = "F3F5F7";
const LIGHT_RED = "FCE8E6";
const LIGHT_YELLOW = "FFF4D6";
const WHITE = "FFFFFF";

const outputPath = path.join(
  __dirname,
  "..",
  "output",
  "synthomer_chester_sc_us_may_2026_report.docx"
);

fs.mkdirSync(path.dirname(outputPath), { recursive: true });

function textRun(text, options = {}) {
  return new TextRun({
    text,
    font: "Aptos",
    size: options.size || 20,
    bold: options.bold || false,
    italics: options.italics || false,
    color: options.color || DARK_TEXT,
    break: options.break || 0,
  });
}

function heading(text, level = HeadingLevel.HEADING_1, options = {}) {
  return new Paragraph({
    heading: level,
    spacing: { before: options.before || 240, after: options.after || 120 },
    children: [
      textRun(text, {
        bold: true,
        size: options.size || (level === HeadingLevel.HEADING_1 ? 30 : 24),
        color: options.color || BUCKMAN_GREEN,
      }),
    ],
  });
}

function paragraph(children, options = {}) {
  return new Paragraph({
    alignment: options.alignment || AlignmentType.LEFT,
    spacing: {
      before: options.before || 0,
      after: options.after === undefined ? 120 : options.after,
      line: options.line || 276,
    },
    bullet: options.bullet ? { level: 0 } : undefined,
    children: Array.isArray(children) ? children : [textRun(children)],
  });
}

function pageBreak() {
  return new Paragraph({
    children: [new PageBreak()],
  });
}

function tableCell(content, options = {}) {
  const children = Array.isArray(content)
    ? content
    : [
        new Paragraph({
          alignment: options.alignment || AlignmentType.LEFT,
          children: [
            textRun(String(content), {
              bold: options.bold || false,
              color: options.color || DARK_TEXT,
              size: options.size || 18,
            }),
          ],
        }),
      ];

  return new TableCell({
    width: options.width
      ? { size: options.width, type: WidthType.PERCENTAGE }
      : undefined,
    verticalAlign: VerticalAlign.CENTER,
    shading: options.fill
      ? {
          type: ShadingType.CLEAR,
          color: "auto",
          fill: options.fill,
        }
      : undefined,
    margins: {
      top: 120,
      bottom: 120,
      left: 120,
      right: 120,
    },
    borders: {
      top: { style: BorderStyle.SINGLE, size: 1, color: "D9E2EC" },
      bottom: { style: BorderStyle.SINGLE, size: 1, color: "D9E2EC" },
      left: { style: BorderStyle.SINGLE, size: 1, color: "D9E2EC" },
      right: { style: BorderStyle.SINGLE, size: 1, color: "D9E2EC" },
    },
    children,
  });
}

function tableHeaderCell(text, width) {
  return tableCell(text, {
    width,
    bold: true,
    color: WHITE,
    fill: BUCKMAN_GREEN,
  });
}

function createTable(headers, rows, widths) {
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    rows: [
      new TableRow({
        tableHeader: true,
        children: headers.map((header, index) =>
          tableHeaderCell(header, widths ? widths[index] : undefined)
        ),
      }),
      ...rows.map(
        (row, rowIndex) =>
          new TableRow({
            children: row.map((cell, cellIndex) =>
              tableCell(cell, {
                fill: rowIndex % 2 === 0 ? WHITE : LIGHT_GRAY,
                width: widths ? widths[cellIndex] : undefined,
              })
            ),
          })
      ),
    ],
  });
}

function statusBadge(status) {
  let fill = LIGHT_GREEN;
  let color = "0F5132";

  if (status === "Action Required") {
    fill = LIGHT_RED;
    color = "842029";
  } else if (status === "Stable") {
    fill = LIGHT_YELLOW;
    color = "664D03";
  }

  return new Table({
    width: { size: 38, type: WidthType.PERCENTAGE },
    rows: [
      new TableRow({
        children: [
          tableCell(`Status: ${status}`, {
            fill,
            color,
            bold: true,
            alignment: AlignmentType.CENTER,
          }),
        ],
      }),
    ],
  });
}

function metricCard(title, value, note, fill = LIGHT_GRAY) {
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    rows: [
      new TableRow({
        children: [
          tableCell(
            [
              new Paragraph({
                spacing: { after: 60 },
                children: [
                  textRun(title, {
                    bold: true,
                    color: BUCKMAN_GREEN,
                    size: 18,
                  }),
                ],
              }),
              new Paragraph({
                spacing: { after: 60 },
                children: [
                  textRun(value, {
                    bold: true,
                    color: DARK_TEXT,
                    size: 28,
                  }),
                ],
              }),
              new Paragraph({
                children: [
                  textRun(note, {
                    color: MUTED_TEXT,
                    size: 17,
                  }),
                ],
              }),
            ],
            { fill }
          ),
        ],
      }),
    ],
  });
}

function titlePage() {
  return [
    new Paragraph({
      spacing: { before: 1200, after: 120 },
      alignment: AlignmentType.CENTER,
      children: [
        textRun("BUCKMAN", {
          bold: true,
          size: 28,
          color: BUCKMAN_GREEN,
        }),
      ],
    }),
    new Paragraph({
      spacing: { before: 240, after: 160 },
      alignment: AlignmentType.CENTER,
      children: [
        textRun("Monthly Cooling Water Performance Report", {
          bold: true,
          size: 42,
          color: DARK_TEXT,
        }),
      ],
    }),
    new Paragraph({
      spacing: { after: 280 },
      alignment: AlignmentType.CENTER,
      children: [
        textRun("Synthomer Chester SC (US)", {
          bold: true,
          size: 30,
          color: BUCKMAN_GREEN,
        }),
      ],
    }),
    new Paragraph({
      spacing: { after: 520 },
      alignment: AlignmentType.CENTER,
      children: [
        textRun("Reporting Month: May 2026", {
          size: 24,
          color: MUTED_TEXT,
        }),
      ],
    }),
    createTable(
      ["Site", "System", "Controller", "Prepared For"],
      [["Synthomer Chester SC (US)", "Cooling Tower", "84253f5ee2c1", "Monthly Performance Review"]],
      [28, 24, 24, 24]
    ),
    paragraph(""),
    paragraph(
      "This report summarizes corrosion control, scale control, microbial control, water efficiency, product efficiency, and proactive system support using the available SCC setpoints, telemetry KPIs, ADE/MDE field data, and service note records for May 2026.",
      { alignment: AlignmentType.CENTER }
    ),
    pageBreak(),
  ];
}

function executiveSummary() {
  return [
    heading("Executive Summary"),

    heading("System Health Check", HeadingLevel.HEADING_2),

    heading("Corrosion Control", HeadingLevel.HEADING_3, { color: DARK_TEXT }),
    statusBadge("Good"),
    paragraph(
      "Mild steel corrosion averaged 0.24 MPY against a target of less than 3.0 MPY. Copper corrosion averaged 0.22 MPY against a target of less than 0.5 MPY. Both corrosion indicators were within the expected performance targets for the reporting period."
    ),

    heading("Scale Control", HeadingLevel.HEADING_3, { color: DARK_TEXT }),
    statusBadge("Good"),
    paragraph(
      "Conductivity averaged 910.5 uS/cm with an SCC programmed control range of 950-1050 uS/cm. The most recent twenty readings were 100% within the SCC programmed control range, indicating stable current control even though the broader-period mean was below the programmed range."
    ),

    heading("Microbial Control", HeadingLevel.HEADING_3, { color: DARK_TEXT }),
    statusBadge("Stable"),
    paragraph(
      "FRC was not available in ADE/MDE field data for this period and will be checked at the upcoming service visit. pH averaged 9.7, turbidity averaged 9.9 NTU, and cell fouling averaged 7.5%. No field microbial test result was available to independently confirm microbial control."
    ),

    heading("Water Efficiency", HeadingLevel.HEADING_2),
    paragraph(
      "Conductivity control was stable in the recent data set, with 100% of the most recent twenty readings inside the SCC programmed control range. No cycles of concentration, makeup water, blowdown, or water loss data were available in the provided reporting context, so water efficiency cannot be fully quantified for this period."
    ),

    heading("Product Efficiency", HeadingLevel.HEADING_2),
    paragraph(
      "Traced Product averaged 106.8 ppm against the SCC programmed control range of 95-105 ppm. Only 10% of the most recent twenty readings were within range, which requires action to improve product control and reduce time above the programmed control band."
    ),

    heading("Proactive System Support", HeadingLevel.HEADING_2),
    paragraph(
      "No service notes were documented for this period, so no Actions Completed could be extracted from the field records. No alarm data was available for this period. Follow-up should confirm FRC during the next service visit and review Traced Product control performance."
    ),

    pageBreak(),
  ];
}

function performanceSummary() {
  const rows = [
    ["MS Corrosion", "0.24 MPY", "< 3.0 MPY", "Good", "Within target"],
    ["Cu Corrosion", "0.22 MPY", "< 0.5 MPY", "Good", "Within target"],
    ["Traced Product", "106.8 ppm", "SCC 95-105 ppm", "Action Required", "10% recent in range"],
    ["Conductivity", "910.5 uS/cm", "SCC 950-1050 uS/cm", "Good", "100% recent in range"],
    ["pH", "9.7", "No SCC programmed control range", "Informational", "Telemetry only"],
    ["Turbidity", "9.9 NTU", "No SCC programmed control range", "Informational", "Telemetry only"],
    ["Cell Fouling", "7.5%", "No SCC programmed control range", "Informational", "Telemetry only"],
    ["FRC", "Not available", "ADE/MDE field data only", "Action Required", "Check at upcoming service visit"],
    ["Service Notes", "None documented", "N/A", "Informational", "No Actions Completed available"],
  ];

  return [
    heading("Performance Summary"),
    paragraph(
      "The SCC programmed control limits were used where available. Standard fallback limits were not used as control limits because site-specific SCC setpoints were present."
    ),
    createTable(
      ["Parameter", "Reported Value", "Control Limit / Target", "Status", "Comment"],
      rows,
      [20, 18, 24, 16, 22]
    ),
    pageBreak(),
  ];
}

function chartsAndComments() {
  const tracedProductRows = [
    ["Mean", "106.8 ppm"],
    ["SCC Range", "95-105 ppm"],
    ["Recent Readings In Range", "2 of 20"],
    ["Percent In Range", "10%"],
    ["Status", "Action Required"],
  ];

  const conductivityRows = [
    ["Mean", "910.5 uS/cm"],
    ["SCC Range", "950-1050 uS/cm"],
    ["Recent Readings In Range", "20 of 20"],
    ["Percent In Range", "100%"],
    ["Status", "Good"],
  ];

  const generalRows = [
    ["pH", "9.7", "No SCC programmed control range"],
    ["Turbidity", "9.9 NTU", "No SCC programmed control range"],
    ["Cell Fouling", "7.5%", "No SCC programmed control range"],
    ["FRC", "Not available", "ADE/MDE field data did not contain FRC"],
  ];

  return [
    heading("Trend Chart 1: Traced Product Control"),
    createTable(["Metric", "Value"], tracedProductRows, [50, 50]),
    paragraph(
      [
        textRun("Comment: ", { bold: true, color: BUCKMAN_GREEN }),
        textRun(
          "Traced Product control requires attention. The recent data set was only 10% within the SCC programmed control range of 95-105 ppm, and the mean value was above the programmed control band."
        ),
      ],
      { before: 120 }
    ),

    heading("Trend Chart 2: Conductivity Control"),
    createTable(["Metric", "Value"], conductivityRows, [50, 50]),
    paragraph(
      [
        textRun("Comment: ", { bold: true, color: BUCKMAN_GREEN }),
        textRun(
          "Conductivity control was good in the recent data set, with all twenty recent readings inside the SCC programmed control range. The reporting-period mean was below the programmed range, so continued monitoring is recommended."
        ),
      ],
      { before: 120 }
    ),

    heading("Supporting Telemetry and Field Data"),
    createTable(["Parameter", "Mean / Result", "Comment"], generalRows, [28, 24, 48]),
    paragraph(
      [
        textRun("Comment: ", { bold: true, color: BUCKMAN_GREEN }),
        textRun(
          "pH, turbidity, and cell fouling were available as telemetry values, but no SCC programmed control ranges were provided for these parameters. FRC was not available in ADE/MDE field data and will need to be checked at the upcoming service visit."
        ),
      ],
      { before: 120 }
    ),

    pageBreak(),
  ];
}

function finalChecklist() {
  const rows = [
    ["SCC setpoints used as control limits", "Complete"],
    ["Fallback standard limits avoided as control limits", "Complete"],
    ["Recent twenty readings used for SCC range percentage", "Complete"],
    ["Traced Product percent in range calculated as 10%", "Complete"],
    ["Conductivity percent in range calculated as 100%", "Complete"],
    ["FRC sourced only from ADE/MDE field data", "Complete"],
    ["Missing FRC stated clearly", "Complete"],
    ["No service notes or Actions Completed invented", "Complete"],
    ["No absolute ORP values included", "Complete"],
    ["No never-in-range statement applied incorrectly", "Complete"],
  ];

  return [
    heading("Final Release Approval Checklist"),
    createTable(["Review Item", "Result"], rows, [72, 28]),
    paragraph(
      "Release approval result: Approved for draft delivery based on the provided reporting context. The primary follow-up items are Traced Product control review and FRC confirmation at the upcoming service visit.",
      { before: 180 }
    ),
  ];
}

const header = new Header({
  children: [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [
        textRun("Buckman | Synthomer Chester SC (US) | May 2026 Cooling Water Performance Report", {
          bold: true,
          color: BUCKMAN_GREEN,
          size: 18,
        }),
      ],
    }),
  ],
});

const footer = new Footer({
  children: [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [
        textRun("Page ", { color: MUTED_TEXT, size: 16 }),
        new TextRun({
          children: [PageNumber.CURRENT],
          font: "Aptos",
          size: 16,
          color: MUTED_TEXT,
        }),
        textRun(" of ", { color: MUTED_TEXT, size: 16 }),
        new TextRun({
          children: [PageNumber.TOTAL_PAGES],
          font: "Aptos",
          size: 16,
          color: MUTED_TEXT,
        }),
      ],
    }),
  ],
});

const doc = new Document({
  creator: "Buckman Report Agent",
  title: "Synthomer Chester SC (US) May 2026 Cooling Water Performance Report",
  description: "Monthly cooling water performance report generated from SCC setpoints, telemetry KPIs, ADE/MDE field data, and service records.",
  styles: {
    default: {
      document: {
        run: {
          font: "Aptos",
          size: 20,
          color: DARK_TEXT,
        },
        paragraph: {
          spacing: {
            line: 276,
            after: 120,
          },
        },
      },
    },
    paragraphStyles: [
      {
        id: "Heading1",
        name: "Heading 1",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: {
          font: "Aptos Display",
          size: 30,
          bold: true,
          color: BUCKMAN_GREEN,
        },
        paragraph: {
          spacing: { before: 240, after: 120 },
        },
      },
      {
        id: "Heading2",
        name: "Heading 2",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: {
          font: "Aptos",
          size: 24,
          bold: true,
          color: BUCKMAN_GREEN,
        },
        paragraph: {
          spacing: { before: 220, after: 100 },
        },
      },
      {
        id: "Heading3",
        name: "Heading 3",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: {
          font: "Aptos",
          size: 21,
          bold: true,
          color: DARK_TEXT,
        },
        paragraph: {
          spacing: { before: 180, after: 80 },
        },
      },
    ],
  },
  sections: [
    {
      properties: {
        page: {
          margin: {
            top: 900,
            right: 720,
            bottom: 900,
            left: 720,
          },
        },
      },
      headers: {
        default: header,
      },
      footers: {
        default: footer,
      },
      children: [
        ...titlePage(),
        ...executiveSummary(),

        heading("Key Performance Indicators"),
        new Table({
          width: { size: 100, type: WidthType.PERCENTAGE },
          rows: [
            new TableRow({
              children: [
                tableCell([metricCard("MS Corrosion", "0.24 MPY", "Target < 3.0 MPY", LIGHT_GREEN)], { width: 50 }),
                tableCell([metricCard("Cu Corrosion", "0.22 MPY", "Target < 0.5 MPY", LIGHT_GREEN)], { width: 50 }),
              ],
            }),
            new TableRow({
              children: [
                tableCell([metricCard("Traced Product", "106.8 ppm", "SCC 95-105 ppm; 10% recent in range", LIGHT_RED)], { width: 50 }),
                tableCell([metricCard("Conductivity", "910.5 uS/cm", "SCC 950-1050 uS/cm; 100% recent in range", LIGHT_GREEN)], { width: 50 }),
              ],
            }),
            new TableRow({
              children: [
                tableCell([metricCard("pH", "9.7", "Telemetry mean", LIGHT_GRAY)], { width: 50 }),
                tableCell([metricCard("FRC", "Not available", "Not found in ADE/MDE field data", LIGHT_YELLOW)], { width: 50 }),
              ],
            }),
          ],
        }),
        paragraph(
          "Overall assessment: corrosion performance was good, conductivity control was good in the recent readings, and Traced Product control requires action. FRC was not available in ADE/MDE field data and should be checked during the upcoming service visit.",
          { before: 180 }
        ),
        pageBreak(),

        ...performanceSummary(),
        ...chartsAndComments(),
        ...finalChecklist(),
      ],
    },
  ],
});

Packer.toBuffer(doc)
  .then((buffer) => {
    fs.writeFileSync(outputPath, buffer);
    console.log(`Word report generated successfully: ${outputPath}`);
  })
  .catch((error) => {
    console.error("Failed to generate Word report:", error);
    process.exitCode = 1;
  });