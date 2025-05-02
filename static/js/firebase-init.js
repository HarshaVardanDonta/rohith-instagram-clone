// Firebase configuration and initialization
// For Firebase JS SDK v7.20.0 and later, measurementId is optional
const firebaseConfig = {
  apiKey: "AIzaSyCHAtyf69L0gihklr9fLokbLaXWqV2rgrc",
  authDomain: "insta-c6412.firebaseapp.com",
  projectId: "insta-c6412",
  storageBucket: "insta-c6412.firebasestorage.app",
  messagingSenderId: "391147470322",
  appId: "1:391147470322:web:fc37bc65a7d0c1ab143f6b",
  measurementId: "G-GE586TNWNH"
};

// Function to ensure we're using the correct Firebase instance
function initializeFirebase() {
  // Check if Firebase is loaded
  if (typeof firebase === 'undefined') {
    console.warn("Firebase SDK not found. Make sure to include the Firebase SDK in your HTML.");
    return null;
  }

  try {
    // Delete any existing app instances to avoid conflicts with old cached data
    try {
      const apps = firebase.apps;
      if (apps.length) {
        console.log("Deleting existing Firebase app instances to ensure fresh initialization");
        apps.forEach(app => app.delete());
      }
    } catch (e) {
      console.log("No existing Firebase apps to delete");
    }

    // Initialize Firebase with our config
    const app = firebase.initializeApp(firebaseConfig);
    console.log("Firebase initialized successfully with project ID:", app.options.projectId);
    
    // Initialize Analytics if available
    if (firebase.analytics) {
      const analytics = firebase.analytics();
      console.log("Firebase Analytics initialized");
    }
    
    return app;
  } catch (error) {
    console.error("Error initializing Firebase:", error);
    return null;
  }
}

// Initialize Firebase when this script loads
const firebaseApp = initializeFirebase();