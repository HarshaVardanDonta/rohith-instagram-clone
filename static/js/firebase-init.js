const firebaseConfig = {
  apiKey: "AIzaSyCHAtyf69L0gihklr9fLokbLaXWqV2rgrc",
  authDomain: "insta-c6412.firebaseapp.com",
  projectId: "insta-c6412",
  storageBucket: "insta-c6412.firebasestorage.app",
  messagingSenderId: "391147470322",
  appId: "1:391147470322:web:fc37bc65a7d0c1ab143f6b",
  measurementId: "G-GE586TNWNH"
};

function initializeFirebase() {
  if (typeof firebase === 'undefined') {
    console.warn("Firebase SDK not found. Make sure to include the Firebase SDK in your HTML.");
    return null;
  }

  try {
    try {
      const existingApps = firebase.apps;
      if (existingApps.length) {
        existingApps.forEach(app => app.delete());
      }
    } catch (e) {
      console.log("No existing Firebase apps to delete");
    }

    const app = firebase.initializeApp(firebaseConfig);
    console.log("Firebase initialized successfully with project ID:", app.options.projectId);
    
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

const firebaseApp = initializeFirebase();