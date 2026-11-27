/*
 * joyeventos: muestra los eventos de los joysticks USB (HID página 1, uso 4 o 5)
 * en macOS. Lo usa probar_joystick.sh (ver docs/JOYSTICK.md).
 *
 * Lista los joysticks en el orden en que IOHIDManager los entrega, con los
 * mismos criterios que el driver "hid" de RetroArch (que numera los puertos
 * en ese orden: #1 = puerto 1), y su locationID (el puerto USB). Después
 * muestra cada botón (número HID: 1 = primer botón; en RetroArch el índice es
 * ese número menos 1), la cruz (hat) y los ejes. Abre los joysticks sin
 * exclusividad: ES-DE y RetroArch los siguen leyendo. No necesita permisos de
 * "Monitoreo de entrada" porque no lee teclados.
 *
 * Compilar: clang -O2 -o joyeventos joyeventos.c -framework IOKit -framework CoreFoundation
 */
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/hid/IOHIDManager.h>
#include <IOKit/hid/IOHIDKeys.h>
#include <stdio.h>
#include <sys/time.h>
#include <time.h>

#define MAX_JOY 8

static IOHIDDeviceRef joys[MAX_JOY];
static int njoys = 0;

static int32_t prop_int(IOHIDDeviceRef d, CFStringRef clave)
{
    int32_t v = 0;
    CFTypeRef ref = IOHIDDeviceGetProperty(d, clave);
    if (ref && CFGetTypeID(ref) == CFNumberGetTypeID())
        CFNumberGetValue((CFNumberRef)ref, kCFNumberSInt32Type, &v);
    return v;
}

static int indice(IOHIDDeviceRef d)
{
    for (int i = 0; i < njoys; i++)
        if (joys[i] == d)
            return i;
    return -1;
}

static void hora(char *s, size_t n)
{
    struct timeval tv;
    struct tm tm;
    gettimeofday(&tv, NULL);
    localtime_r(&tv.tv_sec, &tm);
    size_t k = strftime(s, n, "%H:%M:%S", &tm);
    snprintf(s + k, n - k, ".%03d", (int)(tv.tv_usec / 1000));
}

static void al_conectar(void *ctx, IOReturn r, void *sender, IOHIDDeviceRef d)
{
    (void)ctx; (void)r; (void)sender;
    if (indice(d) >= 0)
        return;
    int i = -1;
    for (int k = 0; k < njoys; k++)
        if (joys[k] == NULL) { i = k; break; }
    if (i < 0) {
        if (njoys >= MAX_JOY)
            return;
        i = njoys++;
    }
    joys[i] = d;
    char nombre[128] = "", h[32];
    CFTypeRef p = IOHIDDeviceGetProperty(d, CFSTR(kIOHIDProductKey));
    if (p && CFGetTypeID(p) == CFStringGetTypeID())
        CFStringGetCString((CFStringRef)p, nombre, sizeof nombre, kCFStringEncodingUTF8);
    hora(h, sizeof h);
    printf("%s conectado #%d: \"%s\" %04x:%04x locationID 0x%08x\n", h, i + 1, nombre,
           prop_int(d, CFSTR(kIOHIDVendorIDKey)) & 0xffff,
           prop_int(d, CFSTR(kIOHIDProductIDKey)) & 0xffff,
           (unsigned)prop_int(d, CFSTR(kIOHIDLocationIDKey)));
    fflush(stdout);
}

static void al_desconectar(void *ctx, IOReturn r, void *sender, IOHIDDeviceRef d)
{
    (void)ctx; (void)r; (void)sender;
    int i = indice(d);
    if (i < 0)
        return;
    joys[i] = NULL;
    char h[32];
    hora(h, sizeof h);
    printf("%s desconectado #%d\n", h, i + 1);
    fflush(stdout);
}

static void al_cambiar(void *ctx, IOReturn r, void *sender, IOHIDValueRef valor)
{
    (void)ctx; (void)r; (void)sender;
    IOHIDElementRef e = IOHIDValueGetElement(valor);
    IOHIDDeviceRef d = IOHIDElementGetDevice(e);
    uint32_t pagina = IOHIDElementGetUsagePage(e);
    uint32_t uso = IOHIDElementGetUsage(e);
    CFIndex v = IOHIDValueGetIntegerValue(valor);
    CFIndex min = IOHIDElementGetLogicalMin(e);
    CFIndex max = IOHIDElementGetLogicalMax(e);
    char texto[96], h[32];

    if (pagina == kHIDPage_Button) {
        snprintf(texto, sizeof texto, "botón %u %s", uso, v ? "apretado" : "suelto");
    } else if (pagina == kHIDPage_GenericDesktop && uso == kHIDUsage_GD_Hatswitch) {
        snprintf(texto, sizeof texto, "cruz (hat) %ld%s", (long)v,
                 v >= min && v <= max ? "" : " (centro)");
    } else if (pagina == kHIDPage_GenericDesktop && uso >= kHIDUsage_GD_X && uso <= kHIDUsage_GD_Rz) {
        static const char *ejes[] = { "X", "Y", "Z", "Rx", "Ry", "Rz" };
        snprintf(texto, sizeof texto, "eje %s = %ld", ejes[uso - kHIDUsage_GD_X], (long)v);
    } else {
        return;   /* página del fabricante y otros: se ignoran */
    }
    hora(h, sizeof h);
    printf("%s #%d (locationID 0x%08x) %s\n", h, indice(d) + 1,
           (unsigned)prop_int(d, CFSTR(kIOHIDLocationIDKey)), texto);
    fflush(stdout);
}

static CFDictionaryRef criterio(uint32_t pagina, uint32_t uso)
{
    CFMutableDictionaryRef dic = CFDictionaryCreateMutable(kCFAllocatorDefault, 0,
        &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
    CFNumberRef p = CFNumberCreate(kCFAllocatorDefault, kCFNumberIntType, &pagina);
    CFNumberRef u = CFNumberCreate(kCFAllocatorDefault, kCFNumberIntType, &uso);
    CFDictionarySetValue(dic, CFSTR(kIOHIDDeviceUsagePageKey), p);
    CFDictionarySetValue(dic, CFSTR(kIOHIDDeviceUsageKey), u);
    CFRelease(p);
    CFRelease(u);
    return dic;
}

int main(void)
{
    IOHIDManagerRef m = IOHIDManagerCreate(kCFAllocatorDefault, kIOHIDOptionsTypeNone);
    CFMutableArrayRef criterios = CFArrayCreateMutable(kCFAllocatorDefault, 0, &kCFTypeArrayCallBacks);
    CFDictionaryRef c1 = criterio(kHIDPage_GenericDesktop, kHIDUsage_GD_Joystick);
    CFDictionaryRef c2 = criterio(kHIDPage_GenericDesktop, kHIDUsage_GD_GamePad);
    CFArrayAppendValue(criterios, c1);
    CFArrayAppendValue(criterios, c2);
    CFRelease(c1);
    CFRelease(c2);
    IOHIDManagerSetDeviceMatchingMultiple(m, criterios);
    CFRelease(criterios);
    IOHIDManagerRegisterDeviceMatchingCallback(m, al_conectar, NULL);
    IOHIDManagerRegisterDeviceRemovalCallback(m, al_desconectar, NULL);
    IOHIDManagerRegisterInputValueCallback(m, al_cambiar, NULL);
    IOHIDManagerScheduleWithRunLoop(m, CFRunLoopGetCurrent(), kCFRunLoopDefaultMode);
    IOReturn r = IOHIDManagerOpen(m, kIOHIDOptionsTypeNone);
    if (r != kIOReturnSuccess)
        fprintf(stderr, "IOHIDManagerOpen: 0x%08x\n", r);
    printf("Mostrando eventos de joysticks (Ctrl-C para salir).\n");
    fflush(stdout);
    CFRunLoopRun();
    return 0;
}
