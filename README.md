<div align="center">

# FAIRmorph Engine

**Domain Validation, Transformation & Packaging Core for FAIR Ecological Data**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FAIR Aligned](https://img.shields.io/badge/FAIR-Aligned-green.svg)](https://www.go-fair.org/fair-principles/)
[![Documentation](https://img.shields.io/badge/Docs-fairmorph.org-brightgreen)](https://fairmorph.github.io/fairmorph-documentation/)

</div>

---

## 📌 Overview

**FAIRmorph Engine** (`fairmorph-engine`) is the headless execution core and domain processing library of the **FAIRmorph** ecosystem. Developed in Python, it encapsulates the business logic, semantic mapping rules, media extraction algorithms, and serialization pipelines required to transform raw field observations and imagery into standardized, scientific data packages.

Operating as a decoupled backend, `fairmorph-engine` can be driven headlessly via command-line execution, automated data pipelines, or directly orchestrated by **FAIRmorph App**.

> 🔒 **Privacy & Data Sovereignty:** All data parsing, EXIF binding, coordinate auditing, and package generation execute 100% locally. Sensitive coordinates, red-list geolocations, and unpublished field notes remain strictly on your local infrastructure.

---

## ✨ Key Capabilities

- 🧬 **Darwin Core Semantic Transformation:** Ingests tabular field records and applies controlled vocabulary mappings, unit standardizations, and structural schema alignments to **Darwin Core (DwC)** standard terms.
- 📸 **EXIF/IPTC Media Record Binding:** Extracts embedded spatial (GPS latitude/longitude/elevation) and temporal (`DateTimeOriginal`) tags directly from field imagery, linking photos to occurrence or sampling event records.
- 🌐 **GIS & Spatial Sanity Auditing:** Performs offline spatial quality control, detecting coordinate inversions (latitude/longitude swaps), datum shifts, and spatial anomalies compatible with **QGIS** mapping workflows.
- 📜 **Cryptographic Provenance Manifests:** Generates immutable, machine-readable provenance logs (`provenance.json`) capturing input/output SHA-256 hashes, applied transformations, and execution metadata for complete scientific reproducibility.
- 📦 **Multi-Target Package Compilation:** Compiles verified assets into publication-ready bundles, including **Darwin Core Archives (DwC-A)**, **Frictionless Data Packages**, and **OGC GeoPackages**.


## 📝 Change Audit Logging & Transparency

To guarantee complete scientific transparency and data hygiene accountability, `fairmorph-engine` maintains a strict separation between high-level dataset provenance and record-level mutation tracking:

* **Separate Execution Logs:** Every data manipulation event is recorded in a dedicated audit stream (`change_audit.log` / `transformations.jsonl`) without altering or bloating the primary dataset output.
* **Row & Cell-Level Tracking:** Tracks exact cell-level diffs, including `before` and `after` states, timestamps, and the specific rule or algorithm that triggered the change.
* **Automated Remediation Audit:** Explicitly documents automated corrections (such as swapped latitude/longitude coordinates, trimmed whitespace, or mapped vocabulary synonyms), allowing researchers to review and verify every automated action.



## 🎯 Supported Standards & Export Targets

- 📦 **Core Data Standards:** Darwin Core (DwC), Ecological Metadata Language (EML v2.2), and Frictionless Data Specifications.
- 🌐 **Global Aggregator Archives:** GBIF (Global Biodiversity Information Facility), OBIS (Ocean Biodiversity Information System), and EMODnet.
- 🗺️ **GIS Interoperability:** OGC GeoPackage (`.gpkg`) and GeoJSON for analysis in QGIS, ArcGIS, and spatial R/Python environments.
- 📚 **Repository Deposit Formats:** Zenodo, PANGAEA, and Dryad bundles for persistent DOI assignment.

---

## 🏗️ Architecture Role

`fairmorph-engine` serves as the domain execution layer beneath **FAIRmorph App**. It contains no UI dependencies, focusing purely on data streaming, schema validation, media parsing, and archive serialization.