"""Example: Using the feedback API."""
import asyncio
import httpx


API_BASE = "http://localhost:8000"


async def main():
    """Demonstrate API usage."""
    print("🧬 GENUS Example: Using the Feedback API\n")
    print("⚠️  Make sure the API server is running:")
    print("   python -m uvicorn genus.api.app:app --reload\n")

    async with httpx.AsyncClient() as client:
        # Create a decision
        print("1. Creating a decision...")
        decision_data = {
            "agent_id": "api-example-agent",
            "decision_type": "route_optimization",
            "input_data": {
                "start": "A",
                "end": "B",
                "options": ["route1", "route2", "route3"]
            },
            "output_data": {
                "selected_route": "route2",
                "estimated_time": 25
            },
            "metadata": {
                "algorithm": "shortest_path",
                "confidence": 0.85
            }
        }

        try:
            response = await client.post(f"{API_BASE}/decisions", json=decision_data)
            response.raise_for_status()
            decision = response.json()
            decision_id = decision["id"]
            print(f"   ✓ Created decision: {decision_id}\n")

            # Submit feedback
            print("2. Submitting positive feedback...")
            feedback_data = {
                "decision_id": decision_id,
                "score": 0.9,
                "label": "success",
                "notes": "Route was optimal, saved 5 minutes!",
                "source": "api_example"
            }

            response = await client.post(f"{API_BASE}/feedback", json=feedback_data)
            response.raise_for_status()
            feedback = response.json()
            print(f"   ✓ Submitted feedback: {feedback['id']}\n")

            # Get decision with feedback
            print("3. Retrieving decision with feedback...")
            response = await client.get(f"{API_BASE}/decisions/{decision_id}")
            response.raise_for_status()
            decision_with_feedback = response.json()

            print(f"   Decision: {decision_with_feedback['decision_type']}")
            print(f"   Agent: {decision_with_feedback['agent_id']}")
            print(f"   Feedback count: {len(decision_with_feedback['feedbacks'])}")
            for fb in decision_with_feedback['feedbacks']:
                print(f"     - {fb['label']} (score: {fb['score']}): {fb['notes']}")

            # List all decisions
            print("\n4. Listing recent decisions...")
            response = await client.get(f"{API_BASE}/decisions?limit=5")
            response.raise_for_status()
            decisions = response.json()
            print(f"   Found {len(decisions)} decisions:")
            for d in decisions[:3]:
                print(f"     - {d['id'][:8]}... ({d['decision_type']})")

            # List all feedback
            print("\n5. Listing recent feedback...")
            response = await client.get(f"{API_BASE}/feedback?limit=5")
            response.raise_for_status()
            feedbacks = response.json()
            print(f"   Found {len(feedbacks)} feedback entries:")
            for fb in feedbacks[:3]:
                print(f"     - {fb['label']} (score: {fb['score']}) for {fb['decision_id'][:8]}...")

            # Get events
            print("\n6. Retrieving system events...")
            response = await client.get(f"{API_BASE}/events?limit=5")
            response.raise_for_status()
            events = response.json()
            print(f"   Found {len(events)} recent events:")
            for event in events[:3]:
                print(f"     - {event['event_type']} from {event.get('source', 'unknown')}")

            print("\n✅ API example completed successfully!")

        except httpx.HTTPStatusError as e:
            print(f"❌ HTTP error: {e.response.status_code} - {e.response.text}")
        except httpx.ConnectError:
            print("❌ Could not connect to API server.")
            print("   Make sure the server is running:")
            print("   python -m uvicorn genus.api.app:app --reload")
        except Exception as e:
            print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
