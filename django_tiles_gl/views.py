import json
from importlib.metadata import metadata
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.http import HttpResponse, HttpResponseNotFound, JsonResponse
from django.shortcuts import render
from django.urls import reverse

from .mbtiles import MissingTileError, open_mbtiles
from .utils import center_from_bounds

DEFAULT_ZOOM = 13
DEFAULT_MINZOOM = 7
DEFAULT_MAXZOOM = 15
WORLD_BOUNDS = [-180, -85.05112877980659, 180, 85.0511287798066]


def tile(request, z, x, y):
    with (open_mbtiles()) as mbtiles:
        try:
            data = mbtiles.tile(z, x, y)
            return HttpResponse(
                content=data,
                headers={
                    "Content-Type": "application/x-protobuf",
                    "Content-Encoding": "gzip",
                },
                status=200,
            )

        except MissingTileError:
            return HttpResponse(
                status=204,
            )


def openmaptiles_style(request):
    if hasattr(settings, "MBTILES_CENTER"):
        center = settings.MBTILES_CENTER
    else:
        with open_mbtiles() as mbtiles:
            metadata = mbtiles.metadata()
            bounds = metadata.get("bounds", WORLD_BOUNDS)
            center = metadata.get("center", center_from_bounds(bounds, DEFAULT_ZOOM))

    base_url = staticfiles_storage.url("django-tiles-gl")
    if not base_url.startswith("http"):
        base_url = request.build_absolute_uri(base_url)

    tilejson_url = request.build_absolute_uri(reverse("tilejson"))

    app_path = Path(__file__).parent
    style_json_path = app_path / "templates" / "django_tiles_gl" / "style.json"
    with style_json_path.open() as f:
        style = json.load(f)

    style["center"] = [center[0], center[1]]
    style["zoom"] = center[2]
    style["sprite"] = base_url + "/sprites/sprite"
    style["glyphs"] = base_url + "/fonts/{fontstack}/{range}.pbf"
    style["sources"] = {"openmaptiles": {"type": "vector", "url": tilejson_url}}

    return JsonResponse(style)


def tilejson(request):
    with open_mbtiles() as mbtiles:
        metadata = mbtiles.metadata()

        # Load valid tilejson keys from the mbtiles metadata
        valid_tilejson_keys = (
            # MUST
            "name",
            "format",
            # SHOULD
            "bounds",
            "center",
            "minzoom",
            "maxzoom",
            # MAY
            "attribution",
            "description",
            "type",
            "version",
        )
        spec = {key: metadata[key] for key in valid_tilejson_keys if key in metadata}

        if spec["format"] == "pbf":
            spec["vector_layers"] = metadata["json"]["vector_layers"]
        else:
            raise NotImplementedError(
                f"Only mbtiles in pbf format are supported. Found {spec['format']}"
            )

        # Optional fields
        spec["scheme"] = metadata.get("scheme", "xyz")
        spec["bounds"] = spec.get("bounds", WORLD_BOUNDS)
        spec["minzoom"] = spec.get("minzoom", DEFAULT_MINZOOM)
        spec["maxzoom"] = spec.get("maxzoom", DEFAULT_MINZOOM)
        spec["center"] = spec.get(
            "center", center_from_bounds(spec["bounds"], DEFAULT_ZOOM)
        )

        # Tile defintions
        tile_url = request.build_absolute_uri(reverse("tile", args=(0, 0, 0)))
        tile_url = tile_url.replace("/0/0/0.pbf", "/{z}/{x}/{y}.pbf")
        spec["tiles"] = [tile_url]

        # Version defintion
        spec["tilejson"] = "3.0.0"

        return JsonResponse(spec)
