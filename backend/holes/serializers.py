"""
Serializers decide the exact JSON shape the website receives.
If the frontend needs a new field, add it here first.
"""

from rest_framework import serializers

from .etl4_bridge import ALLOWED as ETL4_HOLES_WITH_FULL_SPECTRUM
from .tsg_bridge import ALLOWED as TSG_HOLES_WITH_FULL_SPECTRUM
from .models import CoreTray, Hole, Measurement

HOLES_WITH_FULL_SPECTRUM = frozenset(ETL4_HOLES_WITH_FULL_SPECTRUM) | frozenset(TSG_HOLES_WITH_FULL_SPECTRUM)


class HasFullSpectrumMixin(serializers.Serializer):
    """True for the 5 holes restored from database5553/ (etl4_bridge.py) or
    the 15 with a raw TSG package in data5553/ (tsg_bridge.py) - either way a
    full VSWIR/TIR spectrum is instant, not a live NVCL lookup. See the
    /spectral-sample/ endpoint."""

    has_full_spectrum = serializers.SerializerMethodField()

    def get_has_full_spectrum(self, obj):
        return obj.hole_id in HOLES_WITH_FULL_SPECTRUM


class HoleListSerializer(HasFullSpectrumMixin, serializers.ModelSerializer):
    """Small payload - used for the map, where we send hundreds of holes at once.

    Includes elevation/inclination/azimuth (not just lat/lon) so the map can draw
    each hole's straight-line collar-to-toe trajectory as a 3D core without a
    second request per hole - see HoleMap.jsx's "3D core" toggle. It's drawn
    to drawn_length_m, so pass holes from views.holes_with_depth().
    """

    drawn_length_m = serializers.FloatField(read_only=True)

    class Meta:
        model = Hole
        fields = [
            "hole_id", "hole_name", "latitude", "longitude", "elevation_m",
            "inclination_deg", "azimuth_deg", "borehole_length_m", "drawn_length_m",
            "confidential", "has_full_spectrum",
        ]


class HoleDetailSerializer(HasFullSpectrumMixin, serializers.ModelSerializer):
    # from views.holes_with_depth() - borehole_length_m is metres of core
    # scanned, not how deep the hole goes
    logged_from_m = serializers.FloatField(read_only=True)
    logged_to_m = serializers.FloatField(read_only=True)
    drawn_length_m = serializers.FloatField(read_only=True)
    measurement_count = serializers.IntegerField(read_only=True)
    anomaly_count = serializers.IntegerField(read_only=True)
    # {"level": 2, "released": "18/07/2022"} from GSWA's interim index (load_interim), or null
    gswa_level = serializers.SerializerMethodField()

    # {"source": "DASC GDA2020" | "NVCL catalog", "note": why, if a source disagreed, ...}
    # from load_interim's choose_position, or null (NVCL catalog, not in DASC)
    position = serializers.SerializerMethodField()

    def get_gswa_level(self, obj):
        return (obj.catalog or {}).get("gswa_level")

    def get_position(self, obj):
        return (obj.catalog or {}).get("position")

    class Meta:
        model = Hole
        fields = [
            "hole_id", "hole_name", "latitude", "longitude",
            "easting", "northing", "elevation_m", "borehole_length_m",
            "logged_from_m", "logged_to_m", "drawn_length_m",
            "inclination_deg", "azimuth_deg", "confidential",
            "measurement_count", "anomaly_count", "has_full_spectrum", "gswa_level",
            "position",
        ]


class MeasurementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Measurement
        fields = [
            "sample_no", "depth_from_m", "depth_to_m",
            "mineral_1", "mineral_1_pct", "mineral_1_species", "mix",
            "mineral_2", "mineral_2_pct",
            "confidence", "quality_flag", "why",
            "anomaly_score", "is_anomaly",
        ]


class MeasurementWithFeaturesSerializer(MeasurementSerializer):
    """Same as above plus the raw band values - handy when debugging the model."""

    class Meta(MeasurementSerializer.Meta):
        fields = MeasurementSerializer.Meta.fields + ["features"]


class CoreTraySerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = CoreTray
        fields = [
            "tray_no", "depth_from_m", "depth_to_m", "image_url",
            "swir_vnir_mineral", "swir_vnir_group", "swir_vnir_wt_pct", "swir_vnir_pct_of_tray",
            "tir_mineral", "tir_group", "tir_wt_pct", "tir_pct_of_tray",
        ]

    def get_image_url(self, obj):
        if not obj.image:
            return None
        from django.conf import settings
        return f"{settings.MEDIA_URL}{obj.image}"
