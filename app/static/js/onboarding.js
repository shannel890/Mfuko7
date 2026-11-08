(() => {
    "use strict";

    const config = document.getElementById("mfuko-onboarding-config");

    if (!config) return;

    const role = config.dataset.role;
    const storageKey = `mfuko7_onboarding_completed_${role}`;

    const stepsByRole = {
        tenant: [
            {
                title: "Welcome to MFUKO",
                text: "This guided tour will help you find your rent details, payments, and account information."
            },
            {
                title: "Check your rent details",
                text: "Review the rent information on your dashboard. If your rent details are missing, contact your property manager."
            },
            {
                title: "Make a rent payment",
                text: "Use the Make Payment button to open the payment page. Review the amount and payment instructions before confirming any transaction.",
                selector: '[data-onboarding="make-payment"]'
            },
            {
                title: "Review payment history",
                text: "Open Payment History to review available records and check the status of your payments.",
                selector: '[data-onboarding="payment-history"]'
            },
            {
                title: "Manage your profile",
                text: "Open My Profile to review your account information."
            },
            {
                title: "You're ready to begin",
                text: "You can reopen this tour at any time using the Get Started button."
            }
        ],
        landlord: [
            {
                title: "Welcome to your landlord dashboard",
                text: "This tour introduces the main areas for managing your property portfolio and rent collection."
            },
            {
                title: "Review your portfolio",
                text: "Use the dashboard summary to review the property and tenant information available to you."
            },
            {
                title: "Manage properties",
                text: "Open Properties to review your portfolio and access available property-management actions.",
                selector: '[data-onboarding="properties"]'
            },
            {
                title: "Manage tenants",
                text: "Open Tenants to review tenant records and access the tenant-management options available to your account.",
                selector: '[data-onboarding="tenants"]'
            },
            {
                title: "Review payments",
                text: "Open Payments to view the payment records available in your account.",
                selector: '[data-onboarding="payments"]'
            },
            {
                title: "You're ready to begin",
                text: "You can reopen this tour at any time using the Get Started button."
            }
        ]
    };

    const steps = stepsByRole[role];

    if (!steps) return;

    const launchButton = document.createElement("button");
    launchButton.type = "button";
    launchButton.className = "mfuko-onboarding-launch";
    launchButton.textContent = "Get Started";
    launchButton.setAttribute("aria-haspopup", "dialog");

    const backdrop = document.createElement("div");
    backdrop.className = "mfuko-onboarding-backdrop";
    backdrop.hidden = true;

    backdrop.innerHTML = `
        <section
            class="mfuko-onboarding-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="mfuko-onboarding-title"
            aria-describedby="mfuko-onboarding-text"
            tabindex="-1"
        >
            <div class="mfuko-onboarding-progress"></div>
            <h2 id="mfuko-onboarding-title"></h2>
            <p id="mfuko-onboarding-text"></p>
            <div class="mfuko-onboarding-actions">
                <button type="button" data-action="previous">Previous</button>
                <button type="button" data-action="skip">Skip</button>
                <button
                    type="button"
                    class="mfuko-onboarding-next"
                    data-action="next"
                >Next</button>
            </div>
        </section>
    `;

    document.body.append(launchButton, backdrop);

    const dialog = backdrop.querySelector(".mfuko-onboarding-dialog");
    const progress = backdrop.querySelector(".mfuko-onboarding-progress");
    const title = backdrop.querySelector("#mfuko-onboarding-title");
    const text = backdrop.querySelector("#mfuko-onboarding-text");
    const previousButton = backdrop.querySelector('[data-action="previous"]');
    const skipButton = backdrop.querySelector('[data-action="skip"]');
    const nextButton = backdrop.querySelector('[data-action="next"]');

    let currentStep = 0;
    let previouslyFocused = null;

    function renderStep() {
        const step = steps[currentStep];

        progress.textContent = `Step ${currentStep + 1} of ${steps.length}`;
        title.textContent = step.title;
        text.textContent = step.text;

        previousButton.disabled = currentStep === 0;
        previousButton.style.opacity = currentStep === 0 ? "0.5" : "1";

        nextButton.textContent =
            currentStep === steps.length - 1 ? "Finish" : "Next";

        if (step.selector) {
            const target = document.querySelector(step.selector);

            if (target) {
                target.scrollIntoView({
                    behavior: "smooth",
                    block: "nearest"
                });
            }
        }
    }

    function openTutorial() {
        previouslyFocused = document.activeElement;
        currentStep = 0;
        renderStep();

        backdrop.hidden = false;
        dialog.focus();
    }

    function closeTutorial(markCompleted) {
        backdrop.hidden = true;

        if (markCompleted) {
            try {
                localStorage.setItem(storageKey, "true");
            } catch (error) {
                console.warn("Could not save tutorial progress.", error);
            }
        }

        if (previouslyFocused && typeof previouslyFocused.focus === "function") {
            previouslyFocused.focus();
        }
    }

    launchButton.addEventListener("click", openTutorial);

    previousButton.addEventListener("click", () => {
        if (currentStep > 0) {
            currentStep -= 1;
            renderStep();
        }
    });

    nextButton.addEventListener("click", () => {
        if (currentStep < steps.length - 1) {
            currentStep += 1;
            renderStep();
        } else {
            closeTutorial(true);
        }
    });

    skipButton.addEventListener("click", () => {
        closeTutorial(false);
    });

    backdrop.addEventListener("click", event => {
        if (event.target === backdrop) {
            closeTutorial(false);
        }
    });

    document.addEventListener("keydown", event => {
        if (backdrop.hidden) return;

        if (event.key === "Escape") {
            closeTutorial(false);
        }
    });

    try {
        if (localStorage.getItem(storageKey) === "true") {
            launchButton.textContent = "Show Tutorial";
        }
    } catch (error) {
        console.warn("Could not read tutorial progress.", error);
    }
})();