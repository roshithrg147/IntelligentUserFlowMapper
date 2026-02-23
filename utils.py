import os
import hashlib
from function_logger import log_result

@log_result
def save_result(data, filename="user_flow.json", folder="results"):
    try:
        # Create the results directory if it doesn't exist
        os.makedirs(folder, exist_ok=True)
        
        # Determine base name and extension
        base_name, ext = os.path.splitext(filename)
        
        # Start with the original filename
        final_filename = filename
        counter = 1
        
        # Dynamically find a unique filename
        while os.path.exists(os.path.join(folder, final_filename)):
            final_filename = f"{base_name}_{counter}{ext}"
            counter += 1
            
        filepath = os.path.join(folder, final_filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(data)
        print(f"User Flow saved to: {os.path.abspath(filepath)} successfully.")
    except Exception as e:
        print(f"Failed to save JSON: {e}")

@log_result
async def get_state_hash(page):
    try:
        # Optimization: Use a single JS evaluation to gather all element data at once.
        # This is much faster and more resilient than making multiple sequential calls from Python.
        element_signatures = await page.evaluate("""
            () => {
                const elements = document.querySelectorAll("button, a, input, [role='button']");
                return Array.from(elements).map(e => {
                    const tag = e.tagName;
                    const text = (e.innerText || "").trim();
                    const id = e.id || "";
                    return `${tag} : ${id}:${text}`;
                });
            }
        """)
        
        if not element_signatures:
            return hashlib.sha256(b"empty").hexdigest()

        element_signatures.sort()
        combined_string = "|".join(element_signatures)
        return hashlib.sha256(combined_string.encode()).hexdigest()
    except Exception:
        # Return a default hash if the page disappears or evaluation fails
        return hashlib.sha256(b"error").hexdigest()