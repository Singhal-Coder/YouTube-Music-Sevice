import os
import json
from dotenv import load_dotenv
from playwright.async_api import async_playwright

CONFIG_FILE = "config.json"

load_dotenv()
YT_EMAIL = os.getenv("YT_EMAIL")
YT_PASSWORD = os.getenv("YT_PASSWORD")
CHANNEL_ID=os.getenv("CHANNEL_ID")

TARGET_URL = f"https://studio.youtube.com/channel/{CHANNEL_ID}/music"

async def wait_for_2fa_completion(page, wait_secs: int = 60) -> bool | None:
    """
    Detect common Google 2FA prompts (by text / aria hints) and wait for user to complete.
    Returns:
      - False => 2FA prompt not detected (skip)
      - True  => 2FA prompt detected and it disappeared within wait_secs (completed)
      - None  => Timeout or explicit error detected (e.g. "Too many failed attempts")
    Usage: await wait_for_2fa_completion(page, wait_secs=60)
    """

    # human-friendly patterns (case-insensitive, partial match)
    patterns = [
        "check your",           # "Check your device", "Check your <phone>"
        "tap yes",              # "Tap Yes on the notification"
        "2-step verification",
        "2-step verification required",
        "verify it's you",
        "check your device",
        "enter a code"
    ]

    try:
        found_locator = None
        for p in patterns:
            try:
                loc = page.get_by_text(p, exact=False)
                if await loc.count() and await loc.is_visible():
                    found_locator = loc
                    found_text = p
                    break
            except Exception:
                continue

        if not found_locator:
            try:
                aria_loc = page.locator('[aria-live="assertive"], [aria-live="polite"]')
                if await aria_loc.count():
                    # check inner text for our patterns
                    txt = (await aria_loc.inner_text()).lower() if await aria_loc.is_visible() else ""
                    if any(pat in txt for pat in patterns):
                        found_locator = aria_loc
                        found_text = "aria-live"
            except Exception:
                pass

        # no 2FA prompt detected
        if not found_locator:
            return False

        print("[ACTION REQUIRED] 2FA prompt detected ('{}'). Complete verification on your device.".format(found_text))

        try:
            await found_locator.wait_for(state="hidden", timeout=wait_secs * 1000)
            return True
        except TimeoutError:
            print(f"[WARN] 2FA prompt still visible after {wait_secs}s.")
            return None

    except Exception as exc:
        print("[ERROR] waiting for 2FA:", exc)
        return None


async def cookies_valid(page):

    # Check if Google login screen is shown
    await page.wait_for_timeout(2000)
    email_input = await page.query_selector('input[type="email"], #identifierId')

    use_another_button = page.get_by_role("link", name="Use another account")

    if email_input:
        return False
    elif await use_another_button.is_visible():
        await use_another_button.click()
        await page.wait_for_timeout(2000)
        return False

    return True


async def extract_headers_and_tokens(request):
    headers = request.headers
    if "authorization" in headers and "SAPISIDHASH" in headers["authorization"]:
        return headers
    return None

async def refresh_and_save_tokens():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir="chrome-profile",
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
            ]
        )

        page = context.pages[0] if context.pages else await context.new_page()
        

        config_data = {}

        

        event = asyncio.Event()

        async def on_request(request):
            nonlocal config_data, event
            if "creator_music/list_tracks" in request.url and request.method == "POST":
                tokens = await extract_headers_and_tokens(request)
                if tokens:
                    post_data = request.post_data
                    if post_data:
                        try:
                            payload = json.loads(post_data)
                            tokens["SESSION_TOKEN"] = payload.get("context", {}).get("request", {}).get("sessionInfo", {}).get("token")
                            tokens["EATS"] = payload.get("context", {}).get("request", {}).get("eats")
                            tokens['CONSISTENCY_TOKEN_JARS'] = payload.get("context", {}).get("request", {}).get("consistencyTokenJars")
                            tokens['ROLLOUT_TOKEN'] = payload.get("context", {}).get("client", {}).get("rolloutToken")
                            cookies = await context.cookies()
                            required_cookies = ['VISITOR_INFO1_LIVE', 'VISITOR_PRIVACY_METADATA', '__Secure-ROLLOUT_TOKEN', 'HSID', 'SSID', 'APISID', 'SAPISID', '__Secure-1PAPISID', '__Secure-3PAPISID', 'SID', '__Secure-1PSID', '__Secure-3PSID', 'LOGIN_INFO', 'YSC', '__Secure-1PSIDTS', '__Secure-3PSIDTS', 'SIDCC', '__Secure-1PSIDCC', '__Secure-3PSIDCC']
                            cookie_dict = {}
                            for c in cookies:
                                cookie_dict[c['name']] = c['value']
                            cookie_str = "; ".join([f"{key}={cookie_dict[key]}" for key in required_cookies])
                            tokens['cookie'] = cookie_str
                            
                        except:
                            pass
                    config_data = tokens
                    with open(CONFIG_FILE, "w") as f:
                        json.dump(config_data, f, indent=2)
                    print("[SUCCESS] Config saved to", CONFIG_FILE)
                    event.set()

        page.on("request", on_request)
        await page.goto(TARGET_URL)
        if not await cookies_valid(page):
            email_input = await page.query_selector('input[type="email"], #identifierId')
            if email_input:
                print("[INFO] Logging in with credentials...")
                await email_input.fill(YT_EMAIL)
                await page.click("#identifierNext")
                await page.wait_for_timeout(2000)

                await page.fill('input[type="password"]', YT_PASSWORD)
                await page.click("#passwordNext")
                await page.wait_for_timeout(5000)
                if await wait_for_2fa_completion(page, wait_secs=60)==True:
                    print("[INFO] 2FA completed, waiting for 7 seconds...")
                    await page.wait_for_timeout(7000)
            else:
                print("[INFO] Already logged in, skipping manual login.")
        else:
            print("[INFO] Already logged in, skipping manual login.")
        await event.wait()

        await context.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(refresh_and_save_tokens())
