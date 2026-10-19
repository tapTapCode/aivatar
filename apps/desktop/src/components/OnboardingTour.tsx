import { useEffect } from "react";
import { driver, type DriveStep, type Driver } from "driver.js";

import "driver.js/dist/driver.css";

const TOUR_STORAGE_KEY = "aivatar.onboarding.completed.v1";
const START_EVENT = "aivatar:start-onboarding";

function tourSteps(): DriveStep[] {
  const definitions: Array<{ selector: string; title: string; description: string }> = [
    {
      selector: "[data-tour='workspace']",
      title: "Welcome to Aivatar",
      description: "This is your private production workspace for planning, generating, and reviewing polished video exports.",
    },
    {
      selector: "[data-tour='create']",
      title: "Start a production",
      description: "Choose a format to open the right studio preset for an avatar video, visual, presentation, or social cut.",
    },
    {
      selector: "[data-tour='templates']",
      title: "Use a ready-made starting point",
      description: "Templates preselect the format, aspect ratio, and caption treatment so you can focus on the story.",
    },
    {
      selector: "[data-tour='projects']",
      title: "Keep work together",
      description: "Saved projects and recent renders stay in one workspace, ready to review or continue later.",
    },
    {
      selector: "[data-tour='help']",
      title: "Need a refresher?",
      description: "Use Help any time for the production flow. You can also restart this tour from the same place.",
    },
  ];

  return definitions
    .filter(({ selector }) => document.querySelector(selector))
    .map(({ selector, title, description }) => ({
      element: selector,
      popover: { title, description },
    }));
}

export function startOnboardingTour(): Driver | null {
  const steps = tourSteps();
  if (!steps.length) return null;

  const tour = driver({
    steps,
    animate: true,
    smoothScroll: true,
    allowClose: true,
    allowKeyboardControl: true,
    overlayColor: "#050609",
    overlayOpacity: 0.72,
    stagePadding: 8,
    stageRadius: 12,
    popoverClass: "aivatar-driver-popover",
    showProgress: true,
    progressText: "{{current}} of {{total}}",
    nextBtnText: "Next",
    prevBtnText: "Back",
    doneBtnText: "Finish",
    closeBtnLabel: "Close tour",
    onDestroyed: () => {
      try {
        window.localStorage.setItem(TOUR_STORAGE_KEY, "1");
      } catch {
        // Local storage can be unavailable in an embedded or private context.
      }
    },
  });

  tour.drive();
  return tour;
}

export function requestOnboardingTour() {
  window.dispatchEvent(new Event(START_EVENT));
}

export function OnboardingTour() {
  useEffect(() => {
    let activeTour: Driver | null = null;
    let timer: number | undefined;

    const start = () => {
      activeTour?.destroy();
      activeTour = startOnboardingTour();
    };

    const handleStart = () => start();
    window.addEventListener(START_EVENT, handleStart);

    const isOverview = window.location.pathname === "/";
    let completed = false;
    try {
      completed = window.localStorage.getItem(TOUR_STORAGE_KEY) === "1";
    } catch {
      completed = false;
    }
    if (isOverview && !completed) {
      timer = window.setTimeout(start, 500);
    }

    return () => {
      window.removeEventListener(START_EVENT, handleStart);
      if (timer) window.clearTimeout(timer);
      activeTour?.destroy();
    };
  }, []);

  return null;
}
