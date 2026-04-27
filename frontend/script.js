const menuButton = document.querySelector(".menu-toggle");
const siteNav = document.querySelector(".site-nav");
const navLinks = document.querySelectorAll(".site-nav a");

if (menuButton && siteNav) {
  menuButton.addEventListener("click", () => {
    const isOpen = siteNav.classList.toggle("is-open");
    menuButton.setAttribute("aria-expanded", String(isOpen));
  });

  navLinks.forEach((link) => {
    link.addEventListener("click", () => {
      siteNav.classList.remove("is-open");
      menuButton.setAttribute("aria-expanded", "false");
    });
  });
}

const contactForm = document.querySelector(".contact-card");
const formFeedback = document.querySelector(".form-feedback");
const submitButton = contactForm?.querySelector('button[type="submit"]');
const apiBaseTag = document.querySelector('meta[name="school-api-base"]');
const apiBase = apiBaseTag?.getAttribute("content")?.trim();

function getInquiryEndpoint() {
  if (apiBase) {
    return `${apiBase.replace(/\/$/, "")}/api/inquiries`;
  }

  if (window.location.protocol === "file:") {
    return "http://127.0.0.1:8000/api/inquiries";
  }

  return `${window.location.origin}/api/inquiries`;
}

async function parseResponsePayload(response) {
  const responseText = await response.text();

  if (!responseText) {
    return null;
  }

  try {
    return JSON.parse(responseText);
  } catch {
    return { message: responseText };
  }
}

if (contactForm && formFeedback) {
  contactForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    formFeedback.textContent = "";

    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = "Sending...";
    }

    const formData = new FormData(contactForm);
    const payload = {
      name: String(formData.get("name") || "").trim(),
      grade: String(formData.get("grade") || "").trim(),
      phone: String(formData.get("phone") || "").trim(),
      message: String(formData.get("message") || "").trim(),
    };

    try {
      const response = await fetch(getInquiryEndpoint(), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      const result = await parseResponsePayload(response);

      if (!response.ok) {
        throw new Error(
          result?.message || "Unable to submit the enquiry right now. Please check that the backend server is running."
        );
      }

      formFeedback.textContent =
        result?.message || "Thank you. Your enquiry was submitted successfully.";
      contactForm.reset();
    } catch (error) {
      formFeedback.textContent =
        error instanceof Error && error.message.includes("Failed to fetch")
          ? "The enquiry service is not reachable. Start `python server.py` and open the site from `http://127.0.0.1:8000`."
          : error instanceof Error
            ? error.message
            : "Unable to submit the enquiry right now. Please try again.";
    } finally {
      if (submitButton) {
        submitButton.disabled = false;
        submitButton.textContent = "Send Enquiry";
      }
    }
  });
}
