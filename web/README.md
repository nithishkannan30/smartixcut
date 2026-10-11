# SmartixCut web app (React)

Run it while you work (the Python API must also be running on port 8000):

    npm install
    npm run dev          # open http://localhost:5173

Build it for real use (FastAPI then serves it at http://localhost:8000):

    npm run build

## How it is organised

    src/
      main.jsx            starts React, wraps everything in the router and the login provider
      App.jsx             the list of pages (routes)
      api.js              the only place that talks to the Python server
      captionConfig.js    caption colours, sizes, languages... (one place to edit)
      format.js           small helpers (file size, time, download link)
      auth/               who is logged in
        context.js          the shared box
        AuthContext.jsx     fills the box (asks the server, login, signup, logout)
        useAuth.js          how any component reads it
        RequireAuth.jsx     wrap a page in this to make it login-only
      pages/
        AuthPage.jsx        login AND signup (one component, mode="login" | "signup")
        Studio.jsx          the builder: 4 steps + Generate
        JobPage.jsx         one job: progress, then results (address: /jobs/<id>)
      components/         the building blocks of those pages
        UploadStep, BriefStep, CaptionStudio, PhonePreview, FormatStep   the 4 steps
        Progress, Results, ClipCard, FailureCard, History              job screens
        Choice, Switch, Swatches, Section, Header, Logo, Aurora        small shared pieces
      index.css           all styling (colours are the variables at the top)

## The ideas you need

- Component: a function that returns a piece of the page. `<ClipCard clip={c} />` is one clip.
- State: a value React remembers and redraws the page for when it changes (`useState`).
- Effect: code that runs after the page draws, like asking the server for data (`useEffect`).
- Route: an address that shows a page (`/login`, `/jobs/abc`).
- Login: the server sets a cookie we can't read from JavaScript. The browser sends it back on
  every request by itself, so `api.js` needs no token code.
