# Route Fuel Optimization API

The API accepts a **start** and **finish** location inside the USA and returns:

- the driving route geometry,
- a map URL,
- cost-effective fuel stops along the route,
- total estimated fuel spend,
- cache and external API usage details.

The project uses the fuel price CSV as the station price source. It uses **OpenRouteService** for both geocoding and routing, **PostGIS** for spatial station lookup, **Redis** for trip-result caching, and **Celery** for background station geocoding.

---

## Architecture

```text
Client / Postman
    |
    v
Django REST API
    |
    |-- Token auth + rate limit
    |-- Redis cache lookup
    |-- OpenRouteService geocoding for start/finish, cached in DB
    |-- OpenRouteService directions call, one call per cache miss
    |-- PostGIS station filtering near route corridor
    |-- Fuel-stop optimizer
    v
JSON response with route, map URL, stops, and total spend
```

For repeated identical trip searches, Redis returns the previous result without calling OpenRouteService again.

---

## External API choice

This project uses OpenRouteService because it provides both:

- directions/routing API,
- geocoding API.

The API supports authentication through an API key sent in the `Authorization` header. The public API docs describe directions under `/v2/directions/{profile}` and geocoding under `/geocode/search`. OpenRouteService also documents that the API key may be sent through the `Authorization` header for POST and GET requests. OpenRouteService is based on OpenStreetMap data and exposes routing/geocoding services. See OpenRouteService API docs for the current limits and account setup.

---

## Environment variables

Copy the example file:

```bash
cp .env.example .env
```

Set your OpenRouteService key:

```env
OPENROUTESERVICE_API_KEY=your_key_here
OPENROUTESERVICE_BASE_URL=https://api.openrouteservice.org
OPENROUTESERVICE_PROFILE=driving-car
```

Main variables:

```env
DJANGO_SECRET_KEY=change-me
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
DATABASE_URL=postgis://postgres:postgres@db:5432/route_fuel
REDIS_URL=redis://redis:6379/0
CACHE_URL=redis://redis:6379/1
TRIP_CACHE_TTL_SECONDS=3600
HTTP_TIMEOUT_SECONDS=20
OPENROUTESERVICE_API_KEY=your_key_here
```

---

## Run with Docker

```bash
docker compose up --build
```

In another terminal:

```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py import_fuel_prices data/fuel-prices-for-be-assessment.csv
docker compose exec web python manage.py create_api_token --username demo
```

The token command prints a token. Use it in API requests:

```http
Authorization: Token YOUR_TOKEN_HERE
```

---

## Geocode fuel stations

The normal trip API expects stations to already have coordinates.

For a small synchronous batch:

```bash
docker compose exec web python manage.py geocode_stations --limit 100 --sleep-seconds 0.25
```

For Celery background geocoding:

```bash
docker compose exec web python manage.py geocode_all_stations_async --batch-size 500 --sleep-seconds 0.25
```

The Docker Compose file includes a Celery worker:

```bash
docker compose logs -f celery
```

Run repeated batches until all stations are geocoded.

---

## API documentation

Swagger UI:

```text
http://localhost:8000/api/docs/
```

OpenAPI schema:

```text
http://localhost:8000/api/schema/
```

Health check:

```text
http://localhost:8000/health/
```

---

## Main endpoint

```http
POST /api/v1/trips/optimize-fuel/
Authorization: Token YOUR_TOKEN_HERE
Content-Type: application/json
```

Example request:

```json
{
  "start_location": "New York, NY",
  "finish_location": "Chicago, IL",
  "vehicle_range_miles": 500,
  "miles_per_gallon": 10,
  "route_corridor_miles": 15
}
```

Example response shape:

```json
{
  "start_location": "New York, NY",
  "finish_location": "Chicago, IL",
  "route": {
    "distance_miles": 790.34,
    "duration_minutes": 760.2,
    "geometry": {
      "type": "LineString",
      "coordinates": [[-74.006, 40.7128], [-87.6298, 41.8781]]
    },
    "map_url": "https://maps.openrouteservice.org/#/directions/..."
  },
  "fuel_plan": {
    "assumptions": {
      "vehicle_range_miles": 500,
      "miles_per_gallon": 10
    },
    "total_money_spent": "285.44",
    "stops": []
  },
  "external_api_usage": {
    "geocoding_calls": 2,
    "routing_calls": 1,
    "routing_provider": "OpenRouteService",
    "geocoding_provider": "OpenRouteService"
  },
  "cache": {
    "hit": false,
    "key": "trip_plan:..."
  },
  "duration_ms": 432
}
```

On a repeated identical request, `cache.hit` becomes `true`, and no routing/geocoding calls are needed.

---

## How fuel optimization works

1. Geocode the start and finish locations with OpenRouteService.
2. Request a driving route from OpenRouteService once.
3. Use the returned GeoJSON line as the route path.
4. Use PostGIS and a route bounding box to find candidate fuel stations near the route.
5. Calculate each station's nearest route mile and detour distance.
6. For each required fuel segment, choose the lowest-cost reachable station.
7. Estimate total spend using:

```text
total gallons = route distance / miles per gallon
total spend = gallons bought at selected station prices
```

Default assignment assumptions:

```text
vehicle range = 500 miles
fuel economy = 10 MPG
```

---

## Run tests

```bash
docker compose exec web python manage.py test
```

Tests cover:

- serializer validation,
- auth requirement,
- cache key stability,
- distance calculations,
- bounding box logic,
- optimizer short-route behavior,
- unreachable-station edge case.

---

## Production notes

For a real production deployment:

- keep `DJANGO_DEBUG=false`,
- use strong `DJANGO_SECRET_KEY`,
- restrict `DJANGO_ALLOWED_HOSTS`,
- add HTTPS at ingress/load balancer level,
- scale horizontally with more web containers,
- keep `GRANIAN_WORKERS=1` per container and scale containers,
- use managed PostgreSQL/PostGIS and Redis,
- monitor OpenRouteService quota usage,
- consider self-hosted OpenRouteService for high-volume production traffic.
