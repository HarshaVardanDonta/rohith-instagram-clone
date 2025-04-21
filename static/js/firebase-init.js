// Firebase configuration and initialization
// For Firebase JS SDK v7.20.0 and later, measurementId is optional
const firebaseConfig = {
  apiKey: "AIzaSyB-JE76sxkFzA4CcAsHkeb6dtpHReDvcWs",
  authDomain: "instagram-9daa6.firebaseapp.com",
  projectId: "instagram-9daa6",
  storageBucket: "instagram_clone_nithin",
  messagingSenderId: "294561797079",
  appId: "1:294561797079:web:c75a337a2e99f741617192",
  measurementId: "G-M7QTLJPG2Y"
};

// Initialize Firebase
if (typeof firebase !== 'undefined') {
  // Initialize Firebase
  const app = firebase.initializeApp(firebaseConfig);
  
  // Initialize Analytics if available
  if (firebase.analytics) {
    const analytics = firebase.analytics();
  }
  
  console.log("Firebase initialized successfully!");
} else {
  console.warn("Firebase SDK not found. Make sure to include the Firebase SDK in your HTML.");
}