"""
Demo Script: Simulates Lab Companion calling Participant Agent
Demonstrates the full flow without needing Lab Companion to be integrated yet.

Usage:
  # Against deployed Azure endpoint:
  python demo_simulation.py --url https://participant-agent-aieic.azurewebsites.net

  # Against local server:
  python demo_simulation.py --url http://localhost:8001
"""

import httpx
import asyncio
import argparse
import uuid
import time
import json


BASE_URL = "https://participant-agent-aieic-f8dfeda7a0frgvh2.westus3-01.azurewebsites.net"

# Realistic student interaction history for demo
STUDENT_ID = "demo_student_alice"
SESSION_1 = str(uuid.uuid4())
SESSION_2 = str(uuid.uuid4())

INTERACTIONS = [
    # Session 1: Alice struggles with pointers
    {"session_id": SESSION_1, "message": "What is a pointer in C?", "response_time_ms": 1800, "feedback_score": "up"},
    {"session_id": SESSION_1, "message": "I don't understand pointer arithmetic, can you give me a hint?", "response_time_ms": 2200, "feedback_score": "up"},
    {"session_id": SESSION_1, "message": "Why does my program segfault when I dereference this pointer?", "response_time_ms": 3100},
    {"session_id": SESSION_1, "message": "How do I allocate memory with malloc?", "response_time_ms": 1500},
    # Session 2: Alice moves on to data structures, still asks for hints
    {"session_id": SESSION_2, "message": "How do I implement a linked list in C?", "response_time_ms": 2000, "feedback_score": "down"},
    {"session_id": SESSION_2, "message": "Can you give me a hint for reversing a linked list?", "response_time_ms": 2800},
    {"session_id": SESSION_2, "message": "What is the time complexity of searching a linked list?", "response_time_ms": 1200},
]


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_json(data: dict):
    print(json.dumps(data, indent=2, ensure_ascii=False))


async def run_demo(base_url: str):
    async with httpx.AsyncClient(timeout=10.0) as client:

        # ── Step 1: Health check ──────────────────────────────────
        print_section("Step 1: Health Check")
        r = await client.get(f"{base_url}/health")
        print(f"GET /health → {r.status_code}")
        print_json(r.json())

        # ── Step 2: Simulate Lab Companion logging interactions ────
        print_section("Step 2: Simulating Lab Companion — logging student interactions")
        print(f"Student: {STUDENT_ID}")
        print(f"Sessions: 2  |  Total messages: {len(INTERACTIONS)}\n")

        for i, interaction in enumerate(INTERACTIONS, 1):
            payload = {
                "student_id": STUDENT_ID,
                "session_id": interaction["session_id"],
                "message": interaction["message"],
                "response_time_ms": interaction["response_time_ms"],
            }
            if "feedback_score" in interaction:
                payload["feedback_score"] = interaction["feedback_score"]
                
            r = await client.post(f"{base_url}/participant/log", json=payload)
            result = r.json()
            status = "✓" if r.status_code == 200 else "✗"
            print(
                f"  [{i}/{len(INTERACTIONS)}] {status} "
                f"status={r.status_code} feedback={interaction.get('feedback_score', 'omitted')}"
            )
            print(f"  [{i}/{len(INTERACTIONS)}] {status} \"{interaction['message'][:55]}...\""
                  if len(interaction['message']) > 55
                  else f"  [{i}/{len(INTERACTIONS)}] {status} \"{interaction['message']}\"")
            await asyncio.sleep(0.3)

        # ── Step 3: Lab Companion queries context at next session start ──
        print_section("Step 3: Lab Companion requests student context (next session start)")
        print(f"GET /participant/context/{STUDENT_ID}\n")

        r = await client.get(f"{base_url}/participant/context/{STUDENT_ID}")
        context = r.json()
        print_json(context)

        # ── Step 4: Show how Lab Companion would use this ─────────
        print_section("Step 4: How Lab Companion uses the context (demo)")
        print("Lab Companion system prompt would be augmented with:\n")
        print(f'  Total questions : {context["total_questions"]}')
        print(f'  Sessions        : {context["sessions_count"]}')
        print(f'  Avg per session : {context["avg_questions_per_session"]}')
        print(f'  Question types  : {context["question_type_distribution"]}')
        print(f'  Avg hint level  : {context["avg_hint_level"]}')
        print(f'  Per-session freq: {context["session_help_frequency"]}')
        print(f'\n  [AI-generated summary]\n  {context["summary"]}')
        print()
        print("→ Lab Companion can now tailor responses to Alice's learning pattern.")
        print("→ Instructor dashboard can track class-wide trends via Cosmos DB.")

        # ── Step 5: Swagger docs reminder ─────────────────────────
        print_section("Step 5: Interactive API docs")
        print(f"  Swagger UI: {base_url}/docs")
        print(f"  Cosmos DB:  Azure Portal → Data Explorer → aieic-lab → interactions")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Participant Agent demo simulation")
    parser.add_argument("--url", default=BASE_URL, help="API base URL")
    args = parser.parse_args()

    print(f"\nParticipant Agent Demo")
    print(f"Target: {args.url}")
    asyncio.run(run_demo(args.url))
