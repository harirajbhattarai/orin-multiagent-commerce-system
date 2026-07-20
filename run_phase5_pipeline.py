#!/usr/bin/env python3
import sys
import json
from pathlib import Path

# Add the ORIN agents directory to sys.path
BASE_DIR = Path("/data/.openclaw/workspace")
AGENTS_DIR = BASE_DIR / "tools" / "shopify_publisher" / "orin"
sys.path.insert(0, str(AGENTS_DIR))

from hcs_writer_adapter import run_hcs_pipeline_simulation

# Define the run_id from the user's instructions
RUN_ID = "hcs_p5_20260716_110120"
OUTPUT_BASE_DIR = BASE_DIR / "clients" / "hcs_gadgets" / "content_engine" / "automation_state" / "phase5" / RUN_ID

# Load the isolated Job 03 fixture
fixture_job_path = OUTPUT_BASE_DIR / "selected_job_fixture.json"
with open(fixture_job_path, "r", encoding="utf-8") as f:
    fixture_job_data = json.load(f)

# The run_hcs_pipeline_simulation expects the job_number and topic directly from the fixture
# rather than being passed separately.
job_number_for_sim = fixture_job_data["job_number"]
job_topic_for_sim = fixture_job_data["topic"]

# Run the pipeline simulation
# The output_dir ensures all artifacts go into the correct Phase 5 directory
print(f"Running HCS pipeline simulation for Job {job_number_for_sim} to {OUTPUT_BASE_DIR}")
pipeline_result = run_hcs_pipeline_simulation(
    client_id="hcs_gadgets",
    job_number=job_number_for_sim,
    fixture_job_data=fixture_job_data,
    output_dir=OUTPUT_BASE_DIR,
)

# Write the full pipeline result to a JSON file for later parsing
with open(OUTPUT_BASE_DIR / "pipeline_run_result.json", "w", encoding="utf-8") as f:
    json.dump(pipeline_result, f, indent=2, default=str)

# Rename writer_output_03.html to writer_output.html
writer_output_src = OUTPUT_BASE_DIR / f"writer_output_{job_number_for_sim}.html"
writer_output_dst = OUTPUT_BASE_DIR / "writer_output.html"
if writer_output_src.exists():
    writer_output_src.rename(writer_output_dst)
    print(f"Renamed {writer_output_src.name} to {writer_output_dst.name}")
else:
    print(f"WARNING: {writer_output_src.name} not found.")

# Rename selected_job.json to selected_job_fixture.json (if it was overwritten by the simulation)
selected_job_sim_path = OUTPUT_BASE_DIR / "selected_job.json"
if selected_job_sim_path.exists():
    # Only rename if it's different from the original fixture
    with open(selected_job_sim_path, "r", encoding="utf-8") as f_sim:
        sim_content = json.load(f_sim)
    with open(fixture_job_path, "r", encoding="utf-8") as f_orig:
        orig_content = json.load(f_orig)
    if sim_content != orig_content:
        # If the simulation *generated* a new selected_job.json, keep it as 'selected_job_context.json'
        # and preserve the original fixture.
        selected_job_sim_path.rename(OUTPUT_BASE_DIR / "selected_job_context.json")
        print("Renamed selected_job.json to selected_job_context.json to preserve original fixture.")
    else:
        # If it's identical, remove the redundant file created by the simulation
        selected_job_sim_path.unlink()
        print("Removed redundant selected_job.json (identical to fixture).")


print(f"Pipeline simulation script finished. Results written to {OUTPUT_BASE_DIR}")
