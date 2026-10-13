import json
import math
import uuid
from pathlib import Path
from datetime import datetime, timezone

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

#BASE = Path(_file_).parent
BASE = Path(__file__).parent
DATA_FILE = BASE / "reports.json"
UPLOAD_DIR = BASE / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

CATEGORIES = [
    "Pothole",
    "Garbage Overflow",
    "Water Leakage",
    "Streetlight Outage",
    "Other",
]

STATUSES = [
    "Submitted",
    "Under Review",
    "In Progress",
    "Resolved",
]


def load_reports():
    if not DATA_FILE.exists():
        return []
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def save_reports(reports):
    DATA_FILE.write_text(
        json.dumps(reports, indent=2),
        encoding="utf-8",
    )


def distance_m(lat1, lon1, lat2, lon2):
    """Approximate distance between two GPS coordinates."""
    radius = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1) * math.cos(p2)
        * math.sin(dl / 2) ** 2
    )
    return radius * 2 * math.atan2(
        math.sqrt(a), math.sqrt(1 - a)
    )


def find_duplicates(reports, category, lat, lon):
    matches = []
    for report in reports:
        if report["category"] != category:
            continue
        if report["status"] == "Resolved":
            continue

        distance = distance_m(
            lat, lon, report["latitude"], report["longitude"]
        )
        if distance <= 100:
            matches.append(report)

    return matches


def priority_score(severity, report_count):
    # A transparent demonstration rule, not an AI prediction.
    return min(100, severity * 20 + (report_count - 1) * 10)


st.set_page_config(
    page_title="CivicLens AI",
    page_icon="📍",
    layout="wide",
)

st.title("📍 CivicLens AI")
st.subheader("Turn community problems into trackable action")
st.caption(
    "Student prototype — reports are not automatically sent "
    "to a government department."
)

reports = load_reports()

tab_report, tab_map, tab_manage = st.tabs(
    ["📝 Report an Issue", "🗺️ Community Map", "📊 Track Reports"]
)

with tab_report:
    st.header("Report a community problem")

    with st.form("report_form"):
        category = st.selectbox("Problem type", CATEGORIES)
        description = st.text_area(
            "Describe the problem",
            placeholder="Example: A large pothole near the main gate.",
        )
        photo = st.file_uploader(
            "Upload a photo (optional)",
            type=["jpg", "jpeg", "png"],
        )

        col1, col2 = st.columns(2)
        with col1:
            latitude = st.number_input(
                "Latitude", value=20.39, format="%.6f"
            )
        with col2:
            longitude = st.number_input(
                "Longitude", value=78.13, format="%.6f"
            )

        severity = st.slider(
            "How serious is the issue?", 1, 5, 3
        )
        submitted = st.form_submit_button(
            "Submit report", type="primary"
        )

    if submitted:
        if not description.strip():
            st.error("Please describe the problem.")
        elif not (-90 <= latitude <= 90 and
                  -180 <= longitude <= 180):
            st.error("Enter valid geographic coordinates.")
        else:
            duplicates = find_duplicates(
                reports, category, latitude, longitude
            )

            photo_name = None
            if photo is not None:
                photo_name = f"{uuid.uuid4().hex}_{photo.name}"
                (UPLOAD_DIR / photo_name).write_bytes(
                    photo.getvalue()
                )

            report = {
                "id": uuid.uuid4().hex[:8],
                "category": category,
                "description": description.strip(),
                "latitude": latitude,
                "longitude": longitude,
                "severity": severity,
                "priority": priority_score(
                    severity, len(duplicates) + 1
                ),
                "status": "Submitted",
                "created_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "photo": photo_name,
                "duplicate_of": (
                    duplicates[0]["id"] if duplicates else None
                ),
            }

            reports.append(report)
            save_reports(reports)

            if duplicates:
                st.warning(
                    "Possible duplicate found. This report is "
                    f"linked to issue {duplicates[0]['id']}. "
                    "A human should confirm whether they match."
                )
            else:
                st.success("Report submitted successfully!")

            st.info(
                f"Report ID: {report['id']} | "
                f"Priority score: {report['priority']}/100"
            )
            st.rerun()

with tab_map:
    st.header("Community issue map")

    active_reports = [
        r for r in reports if r["status"] != "Resolved"
    ]

    if not reports:
        st.info("Submit a test report to see it on the map.")
    else:
        center_lat = sum(
            r["latitude"] for r in reports
        ) / len(reports)
        center_lon = sum(
            r["longitude"] for r in reports
        ) / len(reports)

        map_view = folium.Map(
            location=[center_lat, center_lon], zoom_start=14
        )

        colors = {
            "Pothole": "red",
            "Garbage Overflow": "green",
            "Water Leakage": "blue",
            "Streetlight Outage": "orange",
            "Other": "purple",
        }

        for report in reports:
            popup = (
                f"<b>{report['category']}</b><br>"
                f"{report['description']}<br>"
                f"Status: {report['status']}<br>"
                f"ID: {report['id']}"
            )
            folium.Marker(
                [report["latitude"], report["longitude"]],
                popup=folium.Popup(popup, max_width=300),
                tooltip=report["category"],
                icon=folium.Icon(
                    color=colors.get(report["category"], "gray")
                ),
            ).add_to(map_view)

        st_folium(map_view, width=None, height=500)

        st.caption(
            f"{len(active_reports)} unresolved report(s) "
            f"out of {len(reports)} total."
        )

with tab_manage:
    st.header("Track and manage reports")

    if not reports:
        st.info("No reports yet.")
    else:
        st.metric("Total reports", len(reports))
        st.metric(
            "Unresolved reports",
            sum(r["status"] != "Resolved" for r in reports),
        )

        for report in reversed(reports):
            with st.expander(
                f"{report['id']} — {report['category']} "
                f"— Priority {report['priority']}"
            ):
                st.write(report["description"])
                st.write(f"Status: {report['status']}")
                st.write(f"Created: {report['created_at']}")

                if report.get("duplicate_of"):
                    st.write(
                        "Possible duplicate of: "
                        + report["duplicate_of"]
                    )

                if report.get("photo"):
                    photo_path = UPLOAD_DIR / report["photo"]
                    if photo_path.exists():
                        st.image(photo_path, width=300)

                options = STATUSES
                current = report["status"]
                new_status = st.selectbox(
                    "Update status",
                    options,
                    index=options.index(current),
                    key=f"status_{report['id']}",
                )

                if st.button(
                    "Save status",
                    key=f"save_{report['id']}",
                ):
                    for item in reports:
                        if item["id"] == report["id"]:
                            item["status"] = new_status
                    save_reports(reports)
                    st.success("Status updated.")
                    st.rerun()

        st.subheader("Reports by category")
        df = pd.DataFrame(reports)
        st.bar_chart(df["category"].value_counts())
