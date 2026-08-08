from playwright.sync_api import sync_playwright
import os

def take_annotated_snapshot(html_path: str, output_image: str):
    absolute_url = "file:///" + os.path.abspath(html_path).replace("\\", "/")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(absolute_url)
        
        # Inject JavaScript to mimic OpenFox's element tagging
        page.evaluate("""
        () => {
            let counter = 1;
            const interactables = document.querySelectorAll('button, input, select, a');
            
            interactables.forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return; // Skip invisible elements
                
                const id = 'e' + counter++;
                
                // Create a small badge
                const badge = document.createElement('div');
                badge.innerText = id;
                badge.style.position = 'absolute';
                badge.style.left = (rect.left + window.scrollX) + 'px';
                badge.style.top = (rect.top + window.scrollY - 10) + 'px';
                badge.style.backgroundColor = 'red';
                badge.style.color = 'white';
                badge.style.fontSize = '12px';
                badge.style.padding = '2px 4px';
                badge.style.borderRadius = '3px';
                badge.style.zIndex = '999999';
                badge.style.pointerEvents = 'none'; // Don't block clicks
                badge.style.fontFamily = 'monospace';
                badge.style.fontWeight = 'bold';
                
                document.body.appendChild(badge);
            });
        }
        """)
        
        # Take screenshot
        page.screenshot(path=output_image, full_page=True)
        print(f"Snapshot taken with element tags! Saved to {output_image}")
        browser.close()

if __name__ == "__main__":
    target = "runs/2026-08-05_0112_bubble_sort/index.html"
    output = "debug/openfox_snapshot.png"
    take_annotated_snapshot(target, output)
