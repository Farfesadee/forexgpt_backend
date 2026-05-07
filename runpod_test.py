
"""
Test RunPod vLLM via OpenAI-compatible route.
The worker-vllm image exposes an OpenAI API via a different input format.
This bypasses the broken native handler that ignores ignore_eos.
"""
import httpx
import json
import asyncio
import certifi
import ssl
import os

RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY")
RUNPOD_ENDPOINT = os.getenv("RUNPOD_ENDPOINT_ID")
MODEL_NAME = "forexgpt/forexgpt-mistral-7b-forex-signals-v1.0"

PROMPT = (
    '<s>[INST] You are ForexGPT. Extract forex trading signals from earnings transcripts. '
    'You MUST respond with ONLY a valid JSON object. No markdown, no bullet points. '
    'Just the raw JSON starting with { and ending with }.\n\n'
    'Required format: {"signal": true/false, "currency_pair": "EUR/USD" or null, '
    '"direction": "LONG" or "SHORT" or "NEUTRAL" or null, '
    '"confidence": 0.0-1.0 or null, "reasoning": "explanation", '
    '"magnitude": "low" or "moderate" or "high" or null, '
    '"time_horizon": "current_quarter" or "next_quarter" or "long_term" or null}\n\n'
    'Analyze this earnings call transcript for forex signals. Respond with ONLY a JSON object.\n\n'
    'Transcript:\n'
    'Our Q1 revenue was impacted by a 4 percent FX headwind, primarily due to '
    'USD strength versus EUR. Our European operations represent approximately '
    '35 percent of total revenue, and we expect this headwind to continue into Q2.\n\n'
    'JSON response: [/INST]'
)


async def test_openai_route():
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())

    # OpenAI completions format via RunPod native endpoint
    payload = {
        "input": {
            "openai_route": "/v1/completions",
            "openai_input": {
                "model": MODEL_NAME,
                "prompt": PROMPT,
                "max_tokens": 512,
                "temperature": 0.1,
                "ignore_eos": True,
            }
        }
    }

    async with httpx.AsyncClient(verify=ssl_ctx, timeout=30) as client:
        r = await client.post(
            f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT}/run",
            headers={"Authorization": f"Bearer {RUNPOD_API_KEY}"},
            json=payload,
        )
        r.raise_for_status()
        job_id = r.json()["id"]
        print(f"[OPENAI_ROUTE] submitted job {job_id}")

        for _ in range(60):
            await asyncio.sleep(5)
            s = await client.get(
                f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT}/status/{job_id}",
                headers={"Authorization": f"Bearer {RUNPOD_API_KEY}"},
            )
            data = s.json()
            status = data.get("status")
            if status == "COMPLETED":
                out = data["output"]
                print(f"[OPENAI_ROUTE] output type: {type(out)}")
                print(f"[OPENAI_ROUTE] FULL OUTPUT: {json.dumps(out)[:1000]}")
                return
            elif status in ("FAILED", "CANCELLED"):
                print(f"[OPENAI_ROUTE] FAILED: {data}")
                return
            else:
                print(f"[OPENAI_ROUTE] {status}...")

        print("[OPENAI_ROUTE] TIMEOUT")


async def test_native_with_sampling_params():
    """
    Test native route but pass params inside 'sampling_params' key
    instead of directly in 'input' — some worker versions require this.
    """
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())

    payload = {
        "input": {
            "prompt": PROMPT,
            "sampling_params": {
                "max_tokens": 512,
                "temperature": 0.1,
                "ignore_eos": True,
            }
        }
    }

    async with httpx.AsyncClient(verify=ssl_ctx, timeout=30) as client:
        r = await client.post(
            f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT}/run",
            headers={"Authorization": f"Bearer {RUNPOD_API_KEY}"},
            json=payload,
        )
        r.raise_for_status()
        job_id = r.json()["id"]
        print(f"\n[SAMPLING_PARAMS] submitted job {job_id}")

        for _ in range(60):
            await asyncio.sleep(5)
            s = await client.get(
                f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT}/status/{job_id}",
                headers={"Authorization": f"Bearer {RUNPOD_API_KEY}"},
            )
            data = s.json()
            status = data.get("status")
            if status == "COMPLETED":
                out = data["output"][0]
                usage = out.get("usage", {})
                tokens = out["choices"][0].get("tokens", [])
                text = out["choices"][0].get("text", "")
                raw = text or "".join(tokens)
                print(f"[SAMPLING_PARAMS] output_tokens={usage.get('output')}")
                print(f"[SAMPLING_PARAMS] RAW: {repr(raw[:300])}")
                return
            elif status in ("FAILED", "CANCELLED"):
                print(f"[SAMPLING_PARAMS] FAILED: {data}")
                return
            else:
                print(f"[SAMPLING_PARAMS] {status}...")

        print("[SAMPLING_PARAMS] TIMEOUT")


async def main():
    print("Test 1: OpenAI-compatible route")
    await test_openai_route()

    print("\nTest 2: Native route with sampling_params nested key")
    await test_native_with_sampling_params()


asyncio.run(main())
