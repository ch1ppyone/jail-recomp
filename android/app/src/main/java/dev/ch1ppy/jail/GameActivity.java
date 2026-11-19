package dev.ch1ppy.jail;

import android.os.Bundle;

import org.libsdl.app.SDLActivity;

/** SDL host for the game. MainActivity owns first-run asset setup. */
public class GameActivity extends SDLActivity {
    @Override
    public void setOrientationBis(int w, int h, boolean resizable, String hint) {
        // The manifest fixes the game to landscape.
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    }

    @Override
    protected String[] getArguments() {
        return MainActivity.gameArguments(this);
    }
}
