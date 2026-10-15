"""
Three tables.

    Hole         one row per drill hole (where it is, how deep, which way it points)
    VocabTerm    one HyLogger concept from GSWA's vocabulary workbook
    Assay        one lab assay interval (WAMEX, from the DASC interim package)
    Measurement  one row per depth interval down that hole
    CoreTray     one row per physical core tray - a photo plus its own
                 mineral call, at tray granularity rather than Measurement's
                 per-metre bins. Real photo + real mineral data only exists
                 for a handful of holes so far (see load_core_trays), so most
                 holes simply have zero CoreTray rows.
"""

from django.db import models


class Hole(models.Model):
    # hole_id is the real-world key (e.g. "H001"), so we use it as the primary key.
    hole_id = models.CharField(max_length=64, primary_key=True)
    hole_name = models.CharField(max_length=255, blank=True)

    latitude = models.FloatField()
    longitude = models.FloatField()
    easting = models.FloatField(null=True, blank=True)
    northing = models.FloatField(null=True, blank=True)

    elevation_m = models.FloatField(null=True, blank=True)
    # The GSWA HyLogger catalog's "Total (m)" (= NVCL's boreholeLength_m):
    # metres of core SCANNED, i.e. Depth to - Depth from - not how deep the
    # hole goes. Logging often starts below the collar, so measurements can
    # run deeper than this. Draw holes to views.holes_with_depth()'s
    # drawn_length_m instead.
    borehole_length_m = models.FloatField(null=True, blank=True)

    # -90 = straight down, 0 = horizontal. Azimuth is degrees clockwise from north.
    inclination_deg = models.FloatField(default=-90.0)
    azimuth_deg = models.FloatField(default=0.0)

    # From WAMEX/WAPIMS in the source catalog. Shown as a badge in the UI,
    # never hidden - hiding rows would misrepresent the dataset.
    confidential = models.BooleanField(default=False)

    # From the GSWA HyLogger catalog (load_gswa_catalog), {} if not in it:
    # {"commodity": ["AU", "CU"], "project", "process_level", "type",
    #  "location", "links": {"drill_report": url, "summary_report",
    #  "summary_histogram", "tray_images", "summary_mineral_logs"}}
    catalog = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "holes"
        ordering = ["hole_id"]

    def __str__(self):
        return f"{self.hole_id} ({self.hole_name})"


class Measurement(models.Model):
    QUALITY_CHOICES = [
        ("ok", "ok"),
        ("low_signal", "low signal"),
        ("missing", "missing"),
    ]

    hole = models.ForeignKey(Hole, on_delete=models.CASCADE, related_name="measurements")
    sample_no = models.IntegerField(null=True, blank=True)

    depth_from_m = models.FloatField()
    depth_to_m = models.FloatField()

    # mineral_1 is the dominant SWIR mineral GROUP (e.g. CHLORITE) - the
    # strongest SWIR-active mineral, not a description of the whole rock.
    # mineral_1_pct is its TSA weight, 0..1: how clearly it dominates.
    mineral_1 = models.CharField(max_length=64, blank=True)
    mineral_1_pct = models.FloatField(null=True, blank=True)
    # The specific mineral behind that group (e.g. Chlorite-Fe vs Chlorite-Mg),
    # from data/build_derived.py. Blank where that hole has no Min1 log.
    mineral_1_species = models.CharField(max_length=64, blank=True)
    mineral_2 = models.CharField(max_length=64, blank=True)
    mineral_2_pct = models.FloatField(null=True, blank=True)

    # 0..1. Anything under CONFIDENCE_THRESHOLD in the frontend renders as greyed out.
    confidence = models.FloatField(default=0.0)
    quality_flag = models.CharField(max_length=32, choices=QUALITY_CHOICES, default="ok")

    # Plain-English reason(s) the confidence isn't higher (e.g. "weak signal;
    # the readings within this metre disagree with each other"), from
    # files/extract.py's real per-check scoring. Blank when confidence is
    # high. This is what makes a low-confidence flag explainable rather than
    # just a colour - shown next to the number, not instead of it.
    why = models.TextField(blank=True)

    # Every band_* column from your CSV lands here as {"band_2200": 0.71, ...}.
    # Using JSON means you can change how many bands you have without a migration.
    features = models.JSONField(default=dict, blank=True)

    # Every group's share of the metre, from data/build_derived.py:
    # {"swir": {"CHLORITE": 60, "WHITE-MICA": 40}, "tir": {"SILICA": 55, ...}}
    # in whole percent, zeros left out. TIR also sees quartz, feldspar and
    # pyroxene, which SWIR can't - often why same-group metres look different.
    mix = models.JSONField(default=dict, blank=True)

    # Filled in by: python manage.py detect_anomalies
    anomaly_score = models.FloatField(null=True, blank=True)  # 0..1, higher = odder
    is_anomaly = models.BooleanField(default=False)

    class Meta:
        db_table = "measurements"
        ordering = ["hole_id", "depth_from_m"]
        indexes = [
            models.Index(fields=["hole", "depth_from_m"]),
            models.Index(fields=["is_anomaly"]),
        ]

    def __str__(self):
        return f"{self.hole_id} {self.depth_from_m}-{self.depth_to_m} m"


class VocabTerm(models.Model):
    """GSWA's HyLogger vocabulary (Hylogger_vocab_working_*.xlsx), loaded by
    load_gswa_catalog. Which terms matter for decisions, and why, lives in
    holes/minerals.py's KEY_TERMS - editable without a reload."""

    slug = models.CharField(max_length=64, primary_key=True)
    label = models.CharField(max_length=128)
    alt_labels = models.CharField(max_length=255, blank=True)
    definition = models.TextField(blank=True)
    broader = models.CharField(max_length=64, blank=True)  # parent's slug
    order = models.IntegerField(default=0)  # row order in the workbook

    class Meta:
        db_table = "vocab_terms"
        ordering = ["order"]

    def __str__(self):
        return self.label


class Assay(models.Model):
    """Lab chemistry for one depth interval, from company reports (WAMEX) as
    compiled in GSWA's DASC interim package - load_interim. The package's own
    disclaimer: no quality control was done on these values, and units are the
    most common error. So values outside what rock can hold are kept apart in
    `suspect` (raw value, for checking against the report), never averaged."""

    hole = models.ForeignKey(Hole, on_delete=models.CASCADE, related_name="assays")
    depth_from_m = models.FloatField()
    depth_to_m = models.FloatField()
    # ppm by element, real measurements only: {"Au": 0.012, "Cu": 340.0}
    values = models.JSONField(default=dict, blank=True)
    # elements the lab reported below its detection limit (coded as negatives)
    below_detection = models.JSONField(default=list, blank=True)
    # implausible values, almost always a unit mix-up: {"Au": 421300.0}
    suspect = models.JSONField(default=dict, blank=True)
    collar_id = models.CharField(max_length=32)  # WAMEX CollarId, to trace back to the report

    class Meta:
        db_table = "assays"
        ordering = ["hole_id", "depth_from_m"]
        indexes = [models.Index(fields=["hole", "depth_from_m"])]

    def __str__(self):
        return f"{self.hole_id} {self.depth_from_m}-{self.depth_to_m} m assay"


class CoreTray(models.Model):
    hole = models.ForeignKey(Hole, on_delete=models.CASCADE, related_name="trays")
    tray_no = models.IntegerField()

    depth_from_m = models.FloatField()
    depth_to_m = models.FloatField()

    # Path under MEDIA_ROOT, e.g. "tray_images/KD1/KD1_0001.jpg".
    image = models.CharField(max_length=255, blank=True)

    # Two independent scans read the same tray: SWIR/VNIR (reflected light,
    # ~450-2500nm - good for clays/micas/carbonates) and TIR (thermal
    # infrared, ~6-14um - good for anhydrous silicates like quartz/feldspar
    # that SWIR/VNIR is largely blind to). Real per-tray dominant mineral +
    # TSG's internal mixture weight + what share of the tray's valid points
    # agreed, for each.
    swir_vnir_mineral = models.CharField(max_length=64, blank=True)
    swir_vnir_group = models.CharField(max_length=64, blank=True)
    swir_vnir_wt_pct = models.FloatField(null=True, blank=True)
    swir_vnir_pct_of_tray = models.FloatField(null=True, blank=True)

    tir_mineral = models.CharField(max_length=64, blank=True)
    tir_group = models.CharField(max_length=64, blank=True)
    tir_wt_pct = models.FloatField(null=True, blank=True)
    tir_pct_of_tray = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = "core_trays"
        ordering = ["hole_id", "depth_from_m"]

    def __str__(self):
        return f"{self.hole_id} tray {self.tray_no}"


class Geology(models.Model):
    """The rock a company logged for one depth interval (WAMEX downhole
    geology, in GSWA's DASC interim package) - load_interim. Most intervals
    carry only the company's own lithology code; GSWA has given a harmonised
    rock name to a few. holes/geology.py groups them; a code alone is shown
    as it is, never guessed at."""

    hole = models.ForeignKey(Hole, on_delete=models.CASCADE, related_name="geology")
    depth_from_m = models.FloatField()
    depth_to_m = models.FloatField()
    code = models.CharField(max_length=64, blank=True)  # the company's lithology code
    name = models.CharField(max_length=255, blank=True)  # the company's lithology name
    rock = models.CharField(max_length=128, blank=True)  # GSWA's harmonised rock (or regolith) name
    collar_id = models.CharField(max_length=32)

    class Meta:
        db_table = "geology"
        ordering = ["hole_id", "depth_from_m"]
        indexes = [models.Index(fields=["hole", "depth_from_m"])]
