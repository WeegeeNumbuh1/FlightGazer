## Provided fonts
These are BDF fonts, a simple bitmap font-format that can be created
by many font tools. Given that these are bitmap fonts, they will look good on
very low resolution screens such as the LED displays.

>[!IMPORTANT]
> The fonts in this directory are only the ones used in the FlightGazer project! Additional ones that were originally bundled can be sourced [here](https://github.com/hzeller/rpi-rgb-led-matrix/tree/master/fonts).

Fonts in this directory (except [`3x5.bdf`](./3x5.bdf), [`4x5.bdf`](./4x5.bdf) and [`3x3.bdf`](./3x3.bdf)) are public domain (see the [README](https://github.com/hzeller/rpi-rgb-led-matrix/tree/master/fonts/README)).

<details><summary><b>Doing things with bdf fonts (Show/Hide)</b></summary>

## Create your own

Fonts are in a human readable and editbable `*.bdf` format, but unless you
like reading and writing pixels in hex, generating them is probably easier :)

You can use any font-editor to generate a BDF font or use the conversion
tool [otf2bdf] to create one from some other font format.

Here is an example how you could create a 30pixel high BDF font from some
TrueType font:

```bash
otf2bdf -v -o myfont.bdf -r 72 -p 30 /path/to/font-Bold.ttf
```

## Getting otf2bdf

Installing the tool should be fairly straight-foward

```
sudo apt-get install otf2bdf
```

## Compiling otf2bdf

If you like to compile otf2bdf, you might notice that the configure script
uses some old way of getting the freetype configuration. There does not seem
to be much activity on the mature code, so let's patch that first:

```
sudo apt-get install -y libfreetype6-dev pkg-config autoconf
git clone https://github.com/jirutka/otf2bdf.git   # check it out
cd otf2bdf
patch -p1 <<"EOF"
--- a/configure.in
+++ b/configure.in
@@ -5,8 +5,8 @@ AC_INIT(otf2bdf.c)
 AC_PROG_CC

 OLDLIBS=$LIBS
-LIBS="$LIBS `freetype-config --libs`"
-CPPFLAGS="$CPPFLAGS `freetype-config --cflags`"
+LIBS="$LIBS `pkg-config freetype2 --libs`"
+CPPFLAGS="$CPPFLAGS `pkg-config freetype2 --cflags`"
 AC_CHECK_LIB(freetype, FT_Init_FreeType, LIBS="$LIBS -lfreetype",[
              AC_MSG_ERROR([Can't find Freetype library! Compile FreeType first.])])
 AC_SUBST(LIBS)
EOF

autoconf       # rebuild configure script
./configure    # run configure
make           # build the software
sudo make install   # install it
```

[otf2bdf]: https://github.com/jirutka/otf2bdf

</details>