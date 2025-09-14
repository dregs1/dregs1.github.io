<?php
// Define o tipo de conteúdo para texto simples.
// Isso garante que o aplicativo receba apenas o texto puro do DNS, sem HTML ou outros dados.
header('Content-Type: text/plain');

// Este é o endereço de DNS que você quer que o aplicativo use.
// Você pode modificar este valor sempre que precisar.
$dns_address = "http://repi.live:8080/c/";

// Imprime o endereço do DNS na resposta HTTP.
echo $dns_address;
?>
