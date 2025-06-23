#include <Arduino.h>
#include "driver/i2s.h"

// ======== Konfiguracja ========
#define I2S_NUM         I2S_NUM_0         // Używany interfejs I2S
#define SAMPLE_RATE     800000            // Próbkowanie ADC: 800 kHz
#define ADC_CHANNEL     ADC1_CHANNEL_0    // GPIO36 (VP), czyli kanał ADC1_CH0
#define READ_LEN        800 * 64          // Liczba próbek na ramkę (51200)

static uint16_t buffer[READ_LEN];         // Bufor danych (16-bitowy dla I2S)

void setupI2S()
{
  // Konfiguracja struktury i2s_config_t
  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX | I2S_MODE_ADC_BUILT_IN), // Master, odbiór, ADC wbudowany
    .sample_rate = SAMPLE_RATE,                   // Częstotliwość próbkowania
    .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT, // 16-bitowe próbki
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,  // Tylko jeden kanał (mono)
    .communication_format = I2S_COMM_FORMAT_STAND_I2S, // Standardowy format I2S
    .intr_alloc_flags = 0,                        // Bez specjalnych flag przerwań
    .dma_buf_count = 64,                          // Liczba buforów DMA
    .dma_buf_len = 800,                           // Długość pojedynczego bufora DMA
    .use_apll = false,                            // Bez użycia APLL
    .tx_desc_auto_clear = false,
    .fixed_mclk = 0
  };

  // Inicjalizacja I2S z powyższą konfiguracją
  i2s_driver_install(I2S_NUM, &i2s_config, 0, NULL);
  i2s_set_adc_mode(ADC_UNIT_1, ADC_CHANNEL); // Ustawienie kanału ADC
  i2s_adc_enable(I2S_NUM);                   // Włączenie ADC przez I2S
}

void setup()
{
  Serial.begin(921600);            // Start UART z prędkością 921600 bps
  Serial.println("ADC I2S test");  // Informacja na start

  // Ustawienie nieużywanych pinów jako INPUT (zabezpieczenie przed floatingiem)
  pinMode(35, INPUT); pinMode(39, INPUT); pinMode(34, INPUT);
  pinMode(32, INPUT); pinMode(33, INPUT); pinMode(25, INPUT);
  pinMode(27, INPUT); pinMode(14, INPUT); pinMode(12, INPUT);
  pinMode(13, INPUT); pinMode(4 , INPUT); pinMode(0 , INPUT);
  pinMode(2 , INPUT); pinMode(15, INPUT); pinMode(26, INPUT);

  delay(1000);         // Krótkie opóźnienie na ustabilizowanie systemu
  setupI2S();          // Uruchomienie I2S + ADC
}

void loop()
{
  size_t bytesRead = 0;

  // Czytanie danych z I2S (blokujące — portMAX_DELAY)
  i2s_read(I2S_NUM, buffer, READ_LEN * sizeof(uint16_t), &bytesRead, portMAX_DELAY);

  int numSamples = bytesRead / sizeof(uint16_t); // Liczba próbek rzeczywiście zebranych

  // ====== Wysyłka przez UART ======

  // 1. Dodaj nagłówek (2 bajty: 0xA5A5), by odbiornik mógł się zsynchronizować
  uint16_t header = 0xA5A5;
  Serial.write((uint8_t*)&header, 2);

  // 2. Wyślij cały bufor binarnie (uint16_t)
  Serial.write((uint8_t*)buffer, numSamples * sizeof(uint16_t));
}
